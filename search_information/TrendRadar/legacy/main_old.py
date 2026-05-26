#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TrendRadar - 嵌入式Linux技术信号监控工具
监控嵌入式Linux开发、BSP工程师、Linux驱动开发相关技术趋势
"""

import os
import sys
import json
import time
import yaml
import logging
import hashlib
import hmac
import base64
import urllib.parse
import glob
import ssl
import socket
import urllib3
from datetime import datetime, timedelta

socket.setdefaulttimeout(30)
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict

import requests
import feedparser
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# 添加通知中心客户端路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'analyse_information', 'shared'))
try:
    from notification_client import add_signal as nc_add_signal, process_queue as nc_process_queue
    NOTIFICATION_CENTER_AVAILABLE = True
except ImportError:
    NOTIFICATION_CENTER_AVAILABLE = False
    print("[WARNING] Notification center client not available")

# 禁用SSL警告（用于解决证书验证问题）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 创建自定义SSL上下文（用于解决TLS版本问题）
def create_ssl_context():
    """创建兼容性更好的SSL上下文"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

# 加载环境变量（优先本地 .env，再加载根目录 .env）
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/trendradar.log', encoding='utf-8')
    ]
)
logger = logging.getLogger('TrendRadar')


class TrendRadar:
    def __init__(self, config_path: str = 'config.yaml'):
        """初始化TrendRadar"""
        self.config = self.load_config(config_path)
        self.signals = []
        self.processed_signals = set()  # 已处理信号的哈希集合
        self.stats = {
            'total_processed': 0,
            'total_duplicate': 0,
            'total_notified': 0,
            'total_dead_letter': 0,
            'total_dead_letter_retried': 0,
            'start_time': datetime.now().isoformat()
        }
        self.pending_signals = []  # 待合并的信号缓冲区
        self.last_merge_time = datetime.now() - timedelta(hours=1)
        self.last_health_check = None
        self.setup_directories()
        self.load_processed_signals()
        
    def load_config(self, config_path: str) -> Dict[str, Any]:
        """加载配置文件并解析环境变量"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return self._resolve_env_vars(config)
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            sys.exit(1)
    
    def _resolve_env_vars(self, obj):
        """递归解析配置中的 ${VAR} 环境变量引用"""
        import re
        if isinstance(obj, str):
            pattern = r'\$\{(\w+)\}'
            def replacer(match):
                var_name = match.group(1)
                value = os.environ.get(var_name, '')
                if not value:
                    logger.warning(f"环境变量 {var_name} 未设置")
                return value
            return re.sub(pattern, replacer, obj)
        elif isinstance(obj, dict):
            return {k: self._resolve_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._resolve_env_vars(item) for item in obj]
        return obj
    
    def setup_directories(self):
        """创建必要的目录"""
        dirs = ['data/signals', 'data/dead_letter', 'logs']
        for d in dirs:
            Path(d).mkdir(parents=True, exist_ok=True)
    
    def load_processed_signals(self):
        """加载已处理信号的哈希记录"""
        hash_file = 'data/processed_signals.json'
        if os.path.exists(hash_file):
            try:
                with open(hash_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.processed_signals = set(data.get('hashes', []))
                    logger.info(f"加载 {len(self.processed_signals)} 条已处理信号记录")
            except Exception as e:
                logger.error(f"加载已处理信号记录失败: {e}")
    
    def save_processed_signals(self):
        """保存已处理信号的哈希记录"""
        hash_file = 'data/processed_signals.json'
        try:
            with open(hash_file, 'w', encoding='utf-8') as f:
                json.dump({'hashes': list(self.processed_signals)}, f)
        except Exception as e:
            logger.error(f"保存已处理信号记录失败: {e}")
    
    def generate_signal_hash(self, signal: Dict[str, Any]) -> str:
        """生成信号的唯一哈希值"""
        content = f"{signal.get('url', '')}{signal.get('title', '')}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def is_duplicate(self, signal: Dict[str, Any]) -> bool:
        """检查信号是否重复"""
        signal_hash = self.generate_signal_hash(signal)
        return signal_hash in self.processed_signals
    
    def add_to_dead_letter(self, signal: Dict[str, Any], error: str, retry_count: int = 0):
        """将失败的信号添加到死信队列"""
        dead_letter_file = 'data/dead_letter/dead_letter.json'
        
        # 加载现有死信队列
        dead_letters = []
        if os.path.exists(dead_letter_file):
            try:
                with open(dead_letter_file, 'r', encoding='utf-8') as f:
                    dead_letters = json.load(f)
            except:
                pass
        
        # 添加新的死信记录
        dead_letter = {
            'signal': signal,
            'error': error,
            'retry_count': retry_count,
            'timestamp': datetime.now().isoformat(),
            'signal_hash': self.generate_signal_hash(signal)
        }
        dead_letters.append(dead_letter)
        
        # 保存死信队列
        try:
            with open(dead_letter_file, 'w', encoding='utf-8') as f:
                json.dump(dead_letters, f, ensure_ascii=False, indent=2)
            logger.warning(f"信号已添加到死信队列: {signal.get('title', '未知')}")
        except Exception as e:
            logger.error(f"保存死信队列失败: {e}")
    
    def get_dead_letter_count(self) -> int:
        """获取死信队列中的信号数量"""
        dead_letter_file = 'data/dead_letter/dead_letter.json'
        if os.path.exists(dead_letter_file):
            try:
                with open(dead_letter_file, 'r', encoding='utf-8') as f:
                    dead_letters = json.load(f)
                return len(dead_letters)
            except:
                pass
        return 0
    
    def retry_dead_letters(self, max_retries: int = 3):
        """重试死信队列中的信号"""
        dead_letter_file = 'data/dead_letter/dead_letter.json'
        if not os.path.exists(dead_letter_file):
            return
        
        try:
            with open(dead_letter_file, 'r', encoding='utf-8') as f:
                dead_letters = json.load(f)
        except:
            return
        
        if not dead_letters:
            return
        
        logger.info(f"尝试重试 {len(dead_letters)} 个死信信号")
        
        remaining_letters = []
        for dead_letter in dead_letters:
            signal = dead_letter['signal']
            retry_count = dead_letter.get('retry_count', 0)
            
            if retry_count >= max_retries:
                logger.warning(f"信号已达最大重试次数，放弃: {signal.get('title', '未知')}")
                continue
            
            # 尝试重新发送通知
            webhook_sent = self.send_webhook(signal)
            dingtalk_sent = self.send_dingtalk(signal)
            
            if webhook_sent or dingtalk_sent:
                logger.info(f"死信信号重试成功: {signal.get('title', '未知')}")
                signal_hash = self.generate_signal_hash(signal)
                self.processed_signals.add(signal_hash)
                self.stats['total_notified'] += 1
                self.stats['total_dead_letter_retried'] += 1
            else:
                # 重试失败，增加重试次数
                dead_letter['retry_count'] = retry_count + 1
                remaining_letters.append(dead_letter)
        
        # 保存剩余的死信信号
        try:
            with open(dead_letter_file, 'w', encoding='utf-8') as f:
                json.dump(remaining_letters, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存死信队列失败: {e}")
    
    def check_keywords(self, text: str) -> List[str]:
        if not text:
            return []

        text_lower = text.lower()
        matched_keywords = []

        categories = ['ai_company', 'welfare', 'industry']
        for category in categories:
            keywords = self.config.get('keywords', {}).get(category, [])
            for keyword in keywords:
                parts = keyword.lower().split()
                if all(part in text_lower for part in parts):
                    matched_keywords.append(keyword)

        return matched_keywords
    
    def calculate_relevance(self, keywords: List[str]) -> float:
        """计算相关性分数（金字塔模型权重）"""
        if not keywords:
            return 0.0
        
        # 金字塔模型权重（3层：AI公司与基金 + 福利 + 嵌入式行业）
        weights = {
            'ai_company': 1.2,    # 第2层：AI公司与基金
            'welfare': 1.0,       # 第3层：福利
            'industry': 0.8       # 第4层：嵌入式行业
        }
        
        score = 0.0
        for category, weight in weights.items():
            category_keywords = self.config.get('keywords', {}).get(category, [])
            for keyword in keywords:
                if keyword in category_keywords:
                    score += weight
        
        # 归一化到0-1（使用3层的最大可能分数）
        return min(score / 3.0, 1.0)
    
    def get_layer_for_keyword(self, keyword: str) -> str:
        """根据关键词判断所属层级"""
        for category in ['ai_company', 'welfare', 'industry']:
            if keyword in self.config.get('keywords', {}).get(category, []):
                return category
        return 'industry'  # 默认为行业层
    
    def calculate_time_decay(self, signal: Dict[str, Any]) -> float:
        """根据层级配置计算时间衰减系数（0-1之间，1表示无衰减）"""
        keywords = signal.get('keywords', [])
        if not keywords:
            return 1.0
        
        # 确定信号所属层级（取最高权重的层级）
        layer = 'industry'
        for keyword in keywords:
            for category in ['ai_company', 'welfare', 'industry']:
                if keyword in self.config.get('keywords', {}).get(category, []):
                    layer = category
                    break
        
        # 获取该层级的时间配置
        time_config = self.config.get('time_config', {}).get(layer, {})
        decay_type = time_config.get('decay_type', 'none')
        
        # 如果没有时间戳，返回1.0
        timestamp_str = signal.get('timestamp', '')
        if not timestamp_str:
            return 1.0
        
        try:
            # 解析时间戳
            if 'T' in timestamp_str:
                signal_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            else:
                signal_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            
            # 计算时间差（天）
            time_diff = (datetime.now() - signal_time).total_seconds() / 86400
            
            # 根据衰减类型计算衰减系数
            if decay_type == 'none':
                return 1.0
            elif decay_type == 'exponential':
                half_life = time_config.get('decay_half_life_days', 3)
                return 0.5 ** (time_diff / half_life)
            elif decay_type == 'linear':
                period = time_config.get('decay_period_days', 30)
                return max(0.0, 1.0 - (time_diff / period))
            elif decay_type == 'slow':
                period = time_config.get('decay_period_days', 90)
                return max(0.5, 1.0 - (time_diff / period * 0.5))
            else:
                return 1.0
        except Exception as e:
            logger.warning(f"计算时间衰减失败: {e}")
            return 1.0
    
    def get_max_items_for_source(self, source: Dict[str, Any]) -> int:
        """根据源的层级获取最大抓取数量"""
        layers = source.get('layers', [4])  # 默认为第4层
        
        # 取所有层级中最大的 max_items_per_source
        max_items = 10  # 默认值
        for layer in layers:
            layer_name = {2: 'ai_company', 3: 'welfare', 4: 'industry'}.get(layer, 'industry')
            time_config = self.config.get('time_config', {}).get(layer_name, {})
            layer_max = time_config.get('max_items_per_source', 10)
            max_items = max(max_items, layer_max)
        
        return max_items
    
    def fetch_rss(self) -> List[Dict[str, Any]]:
        """从RSS源获取信号"""
        signals = []
        rss_sources = self.config.get('sources', {}).get('rss', [])
        
        for source in rss_sources:
            if not source.get('enabled', True):
                continue
                
            try:
                logger.info(f"获取RSS: {source['name']}")
                feed = feedparser.parse(source['url'])
                
                # 根据源的层级获取最大抓取数量
                max_items = self.get_max_items_for_source(source)
                
                for entry in feed.entries[:max_items]:
                    title = entry.get('title', '')
                    summary = entry.get('summary', '')
                    link = entry.get('link', '')
                    
                    content = f"{title} {summary}"
                    keywords = self.check_keywords(content)
                    
                    if keywords:
                        relevance = self.calculate_relevance(keywords)
                        if relevance >= self.config.get('filters', {}).get('min_relevance_score', 0.6):
                            signals.append({
                                'source': source['name'],
                                'title': title,
                                'url': link,
                                'content': summary,
                                'keywords': keywords,
                                'relevance_score': relevance,
                                'timestamp': datetime.now().isoformat()
                            })
                            
            except Exception as e:
                logger.error(f"获取RSS失败 {source['name']}: {e}")
        
        return signals
    
    def fetch_web(self) -> List[Dict[str, Any]]:
        """从网页源获取信号"""
        signals = []
        web_sources = self.config.get('sources', {}).get('web', [])
        
        for source in web_sources:
            if not source.get('enabled', True):
                continue
                
            try:
                logger.info(f"获取网页: {source['name']}")
                
                # 基础headers
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
                
                # 合并配置中的自定义headers（如Cookie）
                if 'headers' in source:
                    headers.update(source['headers'])
                
                # 添加SSL容错处理
                try:
                    response = requests.get(source['url'], headers=headers, timeout=30, verify=True)
                except requests.exceptions.SSLError:
                    logger.warning(f"SSL验证失败，尝试跳过验证: {source['name']}")
                    response = requests.get(source['url'], headers=headers, timeout=30, verify=False)
                except requests.exceptions.ConnectionError as e:
                    if 'SSL' in str(e) or 'TLS' in str(e):
                        logger.warning(f"SSL/TLS连接错误，尝试跳过验证: {source['name']}")
                        response = requests.get(source['url'], headers=headers, timeout=30, verify=False)
                    else:
                        raise
                
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'lxml')
                
                # 根据选择器提取内容
                selector = source.get('selector', '')
                if selector:
                    elements = soup.select(selector)
                    for element in elements[:10]:
                        text = element.get_text(strip=True)
                        link_elem = element.find('a')
                        link = link_elem['href'] if link_elem and link_elem.get('href') else ''
                        
                        keywords = self.check_keywords(text)
                        if keywords:
                            relevance = self.calculate_relevance(keywords)
                            if relevance >= self.config.get('filters', {}).get('min_relevance_score', 0.6):
                                signals.append({
                                    'source': source['name'],
                                    'title': text[:100],
                                    'url': link,
                                    'content': text,
                                    'keywords': keywords,
                                    'relevance_score': relevance,
                                    'timestamp': datetime.now().isoformat()
                                })
                                
            except Exception as e:
                logger.error(f"获取网页失败 {source['name']}: {e}")
        
        return signals
    
    def send_webhook(self, signal: Dict[str, Any], max_retries: int = 3) -> bool:
        """发送Webhook通知（带重试机制）"""
        webhook_config = self.config.get('notifications', {}).get('webhook', {})
        
        if not webhook_config.get('enabled', False):
            return False
            
        for attempt in range(max_retries):
            try:
                url = webhook_config.get('url', '')
                method = webhook_config.get('method', 'POST')
                headers = webhook_config.get('headers', {'Content-Type': 'application/json'})
                
                response = requests.request(
                    method=method,
                    url=url,
                    json=signal,
                    headers=headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    logger.info(f"Webhook发送成功: {signal['title']}")
                    return True
                else:
                    logger.warning(f"Webhook发送失败 (尝试 {attempt + 1}/{max_retries}): {response.status_code}")
                    
            except Exception as e:
                logger.error(f"Webhook发送异常 (尝试 {attempt + 1}/{max_retries}): {e}")
            
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 指数退避
        
        return False
    
    def send_dingtalk(self, signal: Dict[str, Any], max_retries: int = 3) -> bool:
        """发送钉钉通知（带重试机制）"""
        dingtalk_config = self.config.get('notifications', {}).get('dingtalk', {})
        
        if not dingtalk_config.get('enabled', False):
            return False
            
        for attempt in range(max_retries):
            try:
                webhook = dingtalk_config.get('webhook', '')
                secret = dingtalk_config.get('secret', '')
                feedback_url = dingtalk_config.get('feedback_url', 'http://localhost:8080')
                
                # 计算签名
                timestamp = str(round(time.time() * 1000))
                string_to_sign = f"{timestamp}\n{secret}"
                hmac_code = hmac.new(
                    secret.encode('utf-8'),
                    string_to_sign.encode('utf-8'),
                    digestmod=hashlib.sha256
                ).digest()
                sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
                
                # 生成信号哈希
                signal_hash = self.generate_signal_hash(signal)
                
                # URL编码标题
                encoded_title = urllib.parse.quote(signal['title'][:50])
                
                # 构建 ActionCard 消息
                title = f"TrendRadar通知: {signal['title'][:30]}"
                summary = signal['content'][:100] + '...' if len(signal['content']) > 100 else signal['content']
                keywords = ', '.join(signal['keywords'][:3])
                
                markdown_text = f"""## {signal['title'][:50]}

> **来源**: {signal['source']} | **关键词**: {keywords}

**摘要**: {summary}

[查看原文]({signal['url']})

[👍 收藏]({feedback_url}/feedback?hash={signal_hash}&action=favorite) | [👎 忽略]({feedback_url}/feedback?hash={signal_hash}&action=ignore)"""
                
                payload = {
                    "msgtype": "actionCard",
                    "actionCard": {
                        "title": title,
                        "text": markdown_text,
                        "btnOrientation": "0",
                        "singleTitle": "查看详情",
                        "singleURL": signal['url']
                    }
                }
                
                url = f"{webhook}&timestamp={timestamp}&sign={sign}"
                response = requests.post(url, json=payload, timeout=10)
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('errcode') == 0:
                        logger.info(f"钉钉通知发送成功: {signal['title']}")
                        return True
                        
                logger.warning(f"钉钉通知发送失败 (尝试 {attempt + 1}/{max_retries}): {response.text}")
                
            except Exception as e:
                logger.error(f"钉钉通知发送异常 (尝试 {attempt + 1}/{max_retries}): {e}")
            
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 指数退避
        
        return False
    
    def save_signal(self, signal: Dict[str, Any]):
        """保存信号到本地"""
        storage_config = self.config.get('storage', {})
        local_path = storage_config.get('local_path', './data/signals')
        format_type = storage_config.get('format', 'json')
        
        # 生成文件名
        date_str = datetime.now().strftime('%Y%m%d')
        filename = f"{date_str}_{hashlib.md5(signal['title'].encode()).hexdigest()[:8]}.{format_type}"
        filepath = os.path.join(local_path, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                if format_type == 'json':
                    json.dump(signal, f, ensure_ascii=False, indent=2)
                elif format_type == 'csv':
                    # 简单CSV格式
                    f.write(','.join([
                        signal['timestamp'],
                        signal['source'],
                        signal['title'],
                        '|'.join(signal['keywords']),
                        str(signal['relevance_score']),
                        signal['url']
                    ]))
                elif format_type == 'markdown':
                    f.write(f"# {signal['title']}\n\n")
                    f.write(f"- 来源: {signal['source']}\n")
                    f.write(f"- 时间: {signal['timestamp']}\n")
                    f.write(f"- 关键词: {', '.join(signal['keywords'])}\n")
                    f.write(f"- 相关性: {signal['relevance_score']}\n")
                    f.write(f"- 链接: {signal['url']}\n\n")
                    f.write(f"## 内容\n\n{signal['content']}\n")
                    
            logger.info(f"信号已保存: {filepath}")
            
        except Exception as e:
            logger.error(f"保存信号失败: {e}")
    
    def check_source_health(self) -> Dict[str, Any]:
        """检查所有信号源的健康状态"""
        health_report = {
            'timestamp': datetime.now().isoformat(),
            'sources': {},
            'overall_status': 'healthy',
            'failed_count': 0
        }
        
        # 检查RSS源
        rss_sources = self.config.get('sources', {}).get('rss', [])
        for source in rss_sources:
            if not source.get('enabled', True):
                continue
            source_name = source['name']
            try:
                start_time = time.time()
                feed = feedparser.parse(source['url'])
                response_time = time.time() - start_time
                
                if feed.bozo and not feed.entries:
                    status = 'error'
                    error = str(feed.bozo_exception)
                else:
                    status = 'healthy'
                    error = None
                
                health_report['sources'][source_name] = {
                    'type': 'rss',
                    'status': status,
                    'response_time': round(response_time, 2),
                    'entries_count': len(feed.entries),
                    'error': error
                }
            except Exception as e:
                health_report['sources'][source_name] = {
                    'type': 'rss',
                    'status': 'error',
                    'response_time': None,
                    'entries_count': 0,
                    'error': str(e)
                }
                health_report['failed_count'] += 1
        
        # 检查网页源
        web_sources = self.config.get('sources', {}).get('web', [])
        for source in web_sources:
            if not source.get('enabled', True):
                continue
            source_name = source['name']
            try:
                start_time = time.time()
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                response = requests.get(source['url'], headers=headers, timeout=15)
                response_time = time.time() - start_time
                
                if response.status_code == 200:
                    status = 'healthy'
                    error = None
                else:
                    status = 'warning'
                    error = f"HTTP {response.status_code}"
                
                health_report['sources'][source_name] = {
                    'type': 'web',
                    'status': status,
                    'response_time': round(response_time, 2),
                    'status_code': response.status_code,
                    'error': error
                }
            except Exception as e:
                health_report['sources'][source_name] = {
                    'type': 'web',
                    'status': 'error',
                    'response_time': None,
                    'status_code': None,
                    'error': str(e)
                }
                health_report['failed_count'] += 1
        
        # 更新整体状态
        if health_report['failed_count'] > 0:
            health_report['overall_status'] = 'degraded'
        if health_report['failed_count'] >= len(health_report['sources']) / 2:
            health_report['overall_status'] = 'critical'
        
        return health_report
    
    def save_health_report(self, report: Dict[str, Any]):
        """保存健康检查报告"""
        health_file = 'data/health_report.json'
        try:
            with open(health_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            logger.info(f"健康检查完成: {report['overall_status']}，{report['failed_count']} 个源失败")
        except Exception as e:
            logger.error(f"保存健康报告失败: {e}")
    
    def send_health_alert(self, report: Dict[str, Any]):
        """发送健康检查告警（P0级）"""
        if report['overall_status'] == 'healthy':
            return
        
        failed_sources = [name for name, info in report['sources'].items() if info['status'] == 'error']
        alert_msg = f"⚠️ **信号源健康告警通知**\n\n"
        alert_msg += f"**状态**: {report['overall_status']}\n"
        alert_msg += f"**失败源数量**: {report['failed_count']}\n"
        alert_msg += f"**失败源**: {', '.join(failed_sources)}\n"
        alert_msg += f"**检查时间**: {report['timestamp']}\n"
        
        # 发送钉钉告警
        dingtalk_config = self.config.get('notifications', {}).get('dingtalk', {})
        if dingtalk_config.get('enabled', False):
            try:
                webhook = dingtalk_config.get('webhook', '')
                secret = dingtalk_config.get('secret', '')
                
                timestamp = str(round(time.time() * 1000))
                string_to_sign = f"{timestamp}\n{secret}"
                hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
                sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
                
                payload = {
                    "msgtype": "markdown",
                    "markdown": {
                        "title": "TrendRadar 信号源告警通知",
                        "text": alert_msg
                    }
                }
                
                url = f"{webhook}&timestamp={timestamp}&sign={sign}"
                requests.post(url, json=payload, timeout=10)
                logger.warning(f"已发送健康告警: {report['overall_status']}")
            except Exception as e:
                logger.error(f"发送健康告警失败: {e}")
    
    def should_check_health(self) -> bool:
        """判断是否需要进行健康检查"""
        health_config = self.config.get('health_check', {})
        check_interval_hours = health_config.get('interval_hours', 24)
        
        if self.last_health_check is None:
            return True
        
        time_since_last = datetime.now() - self.last_health_check
        return time_since_last >= timedelta(hours=check_interval_hours)
    
    def get_signal_priority(self, signal: Dict[str, Any]) -> str:
        keywords = signal.get('keywords', [])
        source = signal.get('source', '')
        
        industry_sources = [
            'Phoronix', 'LWN.net', 'Hackaday', 'Embedded.com', 
            'EE Times', 'Kernel.org', 'Linux Journal',
            '掘金嵌入式', '嵌入式Linux中文站', '电子发烧友-嵌入式', '21IC-嵌入式'
        ]
        if source in industry_sources:
            return 'P2'
        
        ai_company_keywords = self.config.get('keywords', {}).get('ai_company', [])
        welfare_keywords = self.config.get('keywords', {}).get('welfare', [])
        has_ai_company = any(kw in ai_company_keywords for kw in keywords)
        has_welfare = any(kw in welfare_keywords for kw in keywords)
        
        if has_ai_company or has_welfare:
            return 'P1'
        
        return 'P2'
    
    def merge_and_send_signals(self, force: bool = False):
        """合并并发送信号（10分钟内同类信号合并）"""
        merge_config = self.config.get('merge_push', {})
        merge_window_minutes = merge_config.get('window_minutes', 10)
        
        time_since_last = (datetime.now() - self.last_merge_time).total_seconds() / 60
        
        if not force and time_since_last < merge_window_minutes and len(self.pending_signals) > 0:
            return
        
        if not self.pending_signals:
            self.last_merge_time = datetime.now()
            return
        
        # 按优先级分组
        signals_by_priority = defaultdict(list)
        for signal in self.pending_signals:
            priority = self.get_signal_priority(signal)
            signals_by_priority[priority].append(signal)
        
        # 发送合并后的通知
        for priority, signals in signals_by_priority.items():
            if priority == 'P0':
                # P0级：立即发送每条信号
                for signal in signals:
                    self.send_webhook(signal)
                    self.send_dingtalk(signal)
                    self.stats['total_notified'] += 1
                    
                    # 发送到通知中心
                    if NOTIFICATION_CENTER_AVAILABLE:
                        try:
                            nc_add_signal(signal, source='trendradar')
                        except Exception as e:
                            logger.error(f"Failed to send to notification center: {e}")
            elif priority == 'P1':
                # P1级：合并发送
                merged_msg = self._merge_signals_message(signals, priority)
                self._send_merged_notification(merged_msg, priority)
                
                # 发送到通知中心
                if NOTIFICATION_CENTER_AVAILABLE:
                    try:
                        for signal in signals:
                            nc_add_signal(signal, source='trendradar')
                    except Exception as e:
                        logger.error(f"Failed to send to notification center: {e}")
            else:
                # P2级：只记录，不发送（等待日报）
                self._save_for_daily_report(signals)
                
                # 发送到通知中心（仅记录）
                if NOTIFICATION_CENTER_AVAILABLE:
                    try:
                        for signal in signals:
                            nc_add_signal(signal, source='trendradar')
                    except Exception as e:
                        logger.error(f"Failed to send to notification center: {e}")
        
        # 清空缓冲区
        self.pending_signals = []
        self.last_merge_time = datetime.now()
        logger.info(f"合并推送完成: P0={len(signals_by_priority.get('P0', []))}, P1={len(signals_by_priority.get('P1', []))}, P2={len(signals_by_priority.get('P2', []))}")
    
    def _merge_signals_message(self, signals: List[Dict], priority: str) -> str:
        """合并多条信号为一条消息"""
        msg = f"## 📡 TrendRadar {priority}级信号通知汇总\n\n---\n\n"
        msg += f"**⏰ 时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        msg += f"**📊 数量**: {len(signals)} 条信号\n\n---\n\n"
        
        for i, signal in enumerate(signals[:5], 1):  # 最多显示5条
            msg += f"### {i}. {signal['title'][:50]}\n"
            msg += f"- 来源: {signal['source']}\n"
            msg += f"- 关键词: {', '.join(signal['keywords'][:3])}\n"
            msg += f"- 🔗 [查看原文]({signal['url']})\n\n"
        
        if len(signals) > 5:
            msg += f"\n*...还有 {len(signals) - 5} 条信号*\n"
        
        msg += "\n---\n\n> 💡 *此消息由 TrendRadar 自动生成*"
        return msg
    
    def _send_merged_notification(self, message: str, priority: str):
        """发送合并后的通知"""
        dingtalk_config = self.config.get('notifications', {}).get('dingtalk', {})
        if not dingtalk_config.get('enabled', False):
            return
        
        try:
            webhook = dingtalk_config.get('webhook', '')
            secret = dingtalk_config.get('secret', '')
            
            timestamp = str(round(time.time() * 1000))
            string_to_sign = f"{timestamp}\n{secret}"
            hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
            sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
            
            payload = {
                "msgtype": "actionCard",
                "actionCard": {
                    "title": f"TrendRadar {priority}级通知汇总",
                    "text": message,
                    "btnOrientation": "0",
                    "singleTitle": "查看详情",
                    "singleURL": "https://github.com/wuqiZhu/search_information"
                }
            }
            
            url = f"{webhook}&timestamp={timestamp}&sign={sign}"
            requests.post(url, json=payload, timeout=10)
            logger.info(f"{priority}级合并通知发送成功")
        except Exception as e:
            logger.error(f"发送合并通知失败: {e}")
    
    def _save_for_daily_report(self, signals: List[Dict]):
        """保存P2级信号用于日报"""
        report_file = 'data/daily_report_pending.json'
        try:
            pending = []
            if os.path.exists(report_file):
                with open(report_file, 'r', encoding='utf-8') as f:
                    pending = json.load(f)
            pending.extend(signals)
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(pending, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存日报数据失败: {e}")
    
    def send_daily_report(self):
        """发送每日汇总报告（P2级）"""
        report_file = 'data/daily_report_pending.json'
        if not os.path.exists(report_file):
            return
        
        try:
            with open(report_file, 'r', encoding='utf-8') as f:
                signals = json.load(f)
            
            if not signals:
                return
            
            # 生成日报
            msg = f"## 📊 TrendRadar 每日通知汇总\n\n---\n\n"
            msg += f"**📅 日期**: {datetime.now().strftime('%Y-%m-%d')}\n"
            msg += f"**📊 信号总数**: {len(signals)} 条\n\n---\n\n"
            
            # 按来源分组
            by_source = defaultdict(list)
            for signal in signals:
                by_source[signal['source']].append(signal)
            
            for source, source_signals in by_source.items():
                msg += f"### 📍 {source} ({len(source_signals)}条)\n"
                for signal in source_signals[:3]:
                    msg += f"- {signal['title'][:60]}\n"
                if len(source_signals) > 3:
                    msg += f"- *...还有 {len(source_signals) - 3} 条*\n"
                msg += "\n"
            
            msg += "---\n\n> 💡 *此消息由 TrendRadar 自动生成*"
            
            # 发送日报
            self._send_merged_notification(msg, '日报')
            
            # 清空已发送的信号
            os.remove(report_file)
            logger.info(f"每日汇总发送完成: {len(signals)} 条信号")
        except Exception as e:
            logger.error(f"发送日报失败: {e}")
    
    def generate_dashboard(self):
        """生成仪表盘报告"""
        try:
            import subprocess
            script_path = os.path.join(os.path.dirname(__file__), 'dashboard', 'generate_report.py')
            if os.path.exists(script_path):
                subprocess.run(['python', script_path], capture_output=True, text=True)
                logger.info("仪表盘报告生成完成")
            else:
                logger.warning(f"仪表盘脚本不存在: {script_path}")
        except Exception as e:
            logger.error(f"生成仪表盘失败: {e}")
    
    def generate_weekly_trend(self):
        """生成每周趋势报告"""
        try:
            import subprocess
            script_path = os.path.join(os.path.dirname(__file__), 'dashboard', 'weekly_trend.py')
            if os.path.exists(script_path):
                subprocess.run(['python', script_path], capture_output=True, text=True)
                logger.info("每周趋势报告生成完成")
            else:
                logger.warning(f"趋势分析脚本不存在: {script_path}")
        except Exception as e:
            logger.error(f"生成趋势报告失败: {e}")
    
    def sync_to_obsidian(self):
        """同步信号到 Obsidian 知识库"""
        try:
            import subprocess
            script_path = os.path.join(os.path.dirname(__file__), 'dashboard', 'obsidian_sync.py')
            if os.path.exists(script_path):
                result = subprocess.run(['python', script_path], capture_output=True, text=True)
                if result.returncode == 0:
                    logger.info("Obsidian 同步完成")
                else:
                    logger.error(f"Obsidian 同步失败: {result.stderr}")
            else:
                logger.warning(f"Obsidian 同步脚本不存在: {script_path}")
        except Exception as e:
            logger.error(f"Obsidian 同步失败: {e}")
    
    def generate_recommendations(self):
        """生成个性化推荐"""
        try:
            import subprocess
            script_path = os.path.join(os.path.dirname(__file__), 'dashboard', 'recommendation_engine.py')
            if os.path.exists(script_path):
                result = subprocess.run(['python', script_path], capture_output=True, text=True)
                if result.returncode == 0:
                    logger.info("个性化推荐生成完成")
                else:
                    logger.error(f"推荐生成失败: {result.stderr}")
            else:
                logger.warning(f"推荐引擎脚本不存在: {script_path}")
        except Exception as e:
            logger.error(f"生成推荐失败: {e}")
    
    def enhance_summaries(self):
        """增强信号摘要"""
        try:
            import subprocess
            script_path = os.path.join(os.path.dirname(__file__), 'dashboard', 'smart_summary.py')
            if os.path.exists(script_path):
                result = subprocess.run(['python', script_path], capture_output=True, text=True)
                if result.returncode == 0:
                    logger.info("智能摘要增强完成")
                else:
                    logger.error(f"摘要增强失败: {result.stderr}")
            else:
                logger.warning(f"智能摘要脚本不存在: {script_path}")
        except Exception as e:
            logger.error(f"摘要增强失败: {e}")
    
    def cleanup_old_files(self):
        """清理过期文件"""
        cleanup_config = self.config.get('cleanup', {})
        retention_days = cleanup_config.get('retention_days', 7)
        
        # 清理信号文件
        signals_dir = 'data/signals'
        if os.path.exists(signals_dir):
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            deleted_count = 0
            
            for filepath in glob.glob(os.path.join(signals_dir, '*')):
                try:
                    file_stat = os.stat(filepath)
                    file_date = datetime.fromtimestamp(file_stat.st_mtime)
                    
                    if file_date < cutoff_date:
                        os.remove(filepath)
                        deleted_count += 1
                except Exception as e:
                    logger.error(f"清理文件失败 {filepath}: {e}")
            
            if deleted_count > 0:
                logger.info(f"清理了 {deleted_count} 个过期信号文件")
        
        # 清理旧的日志文件
        logs_dir = 'logs'
        if os.path.exists(logs_dir):
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            
            for filepath in glob.glob(os.path.join(logs_dir, '*.log.*')):
                try:
                    file_stat = os.stat(filepath)
                    file_date = datetime.fromtimestamp(file_stat.st_mtime)
                    
                    if file_date < cutoff_date:
                        os.remove(filepath)
                        logger.info(f"清理旧日志: {filepath}")
                except Exception as e:
                    logger.error(f"清理日志失败 {filepath}: {e}")
    
    def heartbeat(self):
        """心跳检测，记录运行状态"""
        heartbeat_file = 'data/heartbeat.json'
        try:
            heartbeat_data = {
                'timestamp': datetime.now().isoformat(),
                'status': 'running',
                'stats': self.stats,
                'processed_count': len(self.processed_signals),
                'dead_letter_count': self.get_dead_letter_count(),
                'pending_signals_count': len(self.pending_signals)
            }
            with open(heartbeat_file, 'w', encoding='utf-8') as f:
                json.dump(heartbeat_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"心跳检测失败: {e}")
    
    def run(self):
        """运行监控"""
        logger.info("TrendRadar 启动监控...")
        
        # 启动时进行一次健康检查
        if self.should_check_health():
            health_report = self.check_source_health()
            self.save_health_report(health_report)
            self.send_health_alert(health_report)
            self.last_health_check = datetime.now()
        
        while True:
            try:
                # 心跳检测
                self.heartbeat()
                
                # 检查是否需要健康检查
                if self.should_check_health():
                    health_report = self.check_source_health()
                    self.save_health_report(health_report)
                    self.send_health_alert(health_report)
                    self.last_health_check = datetime.now()
                
                # 重试死信队列中的信号
                self.retry_dead_letters()
                
                # 获取信号
                signals = []
                signals.extend(self.fetch_rss())
                signals.extend(self.fetch_web())
                
                # 处理信号
                new_signals = 0
                duplicate_signals = 0
                
                for signal in signals:
                    # 检查是否重复
                    if self.is_duplicate(signal):
                        duplicate_signals += 1
                        self.stats['total_duplicate'] += 1
                        continue
                    
                    # 应用时间衰减到相关性分数
                    time_decay = self.calculate_time_decay(signal)
                    signal['relevance_score'] = signal.get('relevance_score', 0) * time_decay
                    signal['time_decay'] = time_decay
                    
                    # 保存信号
                    self.save_signal(signal)
                    
                    # 添加到待合并队列（分级推送）
                    self.pending_signals.append(signal)
                    
                    # 记录已处理信号
                    signal_hash = self.generate_signal_hash(signal)
                    self.processed_signals.add(signal_hash)
                    self.signals.append(signal)
                    new_signals += 1
                    self.stats['total_processed'] += 1
                
                # 合并并发送信号（分级推送）
                self.merge_and_send_signals()
                
                # 处理通知中心队列
                if NOTIFICATION_CENTER_AVAILABLE:
                    try:
                        nc_process_queue()
                    except Exception as e:
                        logger.error(f"Failed to process notification center queue: {e}")
                
                # 保存已处理信号记录
                self.save_processed_signals()
                
                # 输出统计信息
                dead_letter_count = self.get_dead_letter_count()
                logger.info(f"本轮获取 {len(signals)} 个信号，新增 {new_signals} 个，重复 {duplicate_signals} 个")
                logger.info(f"累计统计: 处理 {self.stats['total_processed']} 个，重复 {self.stats['total_duplicate']} 个，通知 {self.stats['total_notified']} 个，死信队列 {dead_letter_count} 个")
                
                # 检查是否需要发送日报（每天20:00发送）
                now = datetime.now()
                if now.hour == 20 and now.minute < 30:
                    self.send_daily_report()
                
                # 每天清理一次过期文件
                if now.hour == 3 and now.minute < 30:
                    self.cleanup_old_files()
                
                # 每天生成仪表盘报告（每天6:00和18:00）
                if (now.hour == 6 or now.hour == 18) and now.minute < 30:
                    self.generate_dashboard()
                
                # 每周一生成趋势报告（周一8:00）
                if now.weekday() == 0 and now.hour == 8 and now.minute < 30:
                    self.generate_weekly_trend()
                
                # 每小时同步到 Obsidian
                if now.minute < 30:
                    self.sync_to_obsidian()
                
                # 每天生成个性化推荐（每天9:00）
                if now.hour == 9 and now.minute < 30:
                    self.generate_recommendations()
                
                # 每天增强摘要（每天10:00）
                if now.hour == 10 and now.minute < 30:
                    self.enhance_summaries()
                
                # 等待下一轮
                interval = self.config.get('scheduler', {}).get('interval_minutes', 30)
                logger.info(f"等待 {interval} 分钟后进行下一轮检查...")
                time.sleep(interval * 60)
                
            except KeyboardInterrupt:
                logger.info("用户中断，停止监控")
                self.save_processed_signals()
                self.merge_and_send_signals(force=True)
                self.print_stats()
                break
            except Exception as e:
                logger.error(f"运行异常: {e}")
                time.sleep(60)  # 出错后等待1分钟重试
    
    def print_stats(self):
        """打印统计信息"""
        logger.info("=" * 50)
        logger.info("运行统计:")
        logger.info(f"  开始时间: {self.stats['start_time']}")
        logger.info(f"  结束时间: {datetime.now().isoformat()}")
        logger.info(f"  处理信号: {self.stats['total_processed']} 个")
        logger.info(f"  重复信号: {self.stats['total_duplicate']} 个")
        logger.info(f"  发送通知: {self.stats['total_notified']} 个")
        logger.info(f"  死信队列: {self.get_dead_letter_count()} 个")
        logger.info(f"  死信加入: {self.stats['total_dead_letter']} 次")
        logger.info(f"  死信重试成功: {self.stats['total_dead_letter_retried']} 次")
        logger.info("=" * 50)


def main():
    """主函数"""
    print("=" * 50)
    print("TrendRadar - 嵌入式Linux技术信号监控")
    print("=" * 50)
    print()
    print("监控关键词: 嵌入式Linux、BSP开发、Linux内核、设备驱动等")
    print("通知方式: Webhook(n8n) / 钉钉 / 邮箱")
    print()
    print("按 Ctrl+C 停止监控")
    print("=" * 50)
    print()
    
    radar = TrendRadar()
    radar.run()


if __name__ == '__main__':
    main()
