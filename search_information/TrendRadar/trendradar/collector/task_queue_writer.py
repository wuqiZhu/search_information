# -*- coding: utf-8 -*-
"""
任务队列写入器 - 终端1专用
将分析结果写入共享任务队列，供终端2读取
"""

import json
import os
import sys
import time
from datetime import datetime

# Linux下使用fcntl实现文件锁
if sys.platform != 'win32':
    import fcntl
    USE_FCNTL = True
else:
    USE_FCNTL = False
    import msvcrt


class TaskQueueWriter:
    """任务队列写入器"""
    
    # 默认队列路径
    DEFAULT_QUEUE_FILE = "/data/tasks/queue.json"
    
    def __init__(self, queue_file=None):
        """
        初始化
        
        Args:
            queue_file: 队列文件路径，默认为 /data/tasks/queue.json
        """
        self.queue_file = queue_file or self.DEFAULT_QUEUE_FILE
        self.lock_file = self.queue_file + ".lock"
        self._ensure_dir()
    
    def _ensure_dir(self):
        """确保目录存在"""
        queue_dir = os.path.dirname(self.queue_file)
        if queue_dir and not os.path.exists(queue_dir):
            os.makedirs(queue_dir, exist_ok=True)
    
    def _read_queue(self):
        """
        读取队列文件
        
        Returns:
            dict: 队列数据
        """
        if not os.path.exists(self.queue_file):
            return {"version": "1.0", "last_updated": "", "batches": []}
        
        try:
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"version": "1.0", "last_updated": "", "batches": []}
    
    def _write_queue(self, data):
        """
        写入队列文件
        
        Args:
            data: 要写入的数据
        
        Returns:
            bool: 是否写入成功
        """
        try:
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[QueueWriter] 写入失败: {e}")
            return False
    
    def _acquire_lock(self, timeout=30):
        """
        获取排他锁
        
        Args:
            timeout: 超时时间（秒）
        
        Returns:
            file or None: 锁文件句柄
        """
        start_time = time.time()
        
        while True:
            try:
                fd = open(self.lock_file, 'w')
                if USE_FCNTL:
                    fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:
                    msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
                return fd
            except (IOError, OSError):
                if 'fd' in locals():
                    fd.close()
                if time.time() - start_time >= timeout:
                    return None
                time.sleep(0.1)
    
    def _release_lock(self, fd):
        """
        释放锁
        
        Args:
            fd: 锁文件句柄
        """
        if fd:
            try:
                if USE_FCNTL:
                    fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
                else:
                    try:
                        fd.seek(0)
                        msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
                    except:
                        pass
                fd.close()
            except:
                pass
    
    def write_analysis_result(self, analysis_data, priority="normal"):
        """
        将分析结果写入任务队列
        
        Args:
            analysis_data: 分析结果数据，包含:
                - news_count: 新闻数量
                - sentiment_score: 情绪分数 (0-1)
                - key_themes: 关键主题列表
                - ai_summary: AI摘要
                - alerts: 预警列表
            priority: 优先级 ("high", "normal", "low")
        
        Returns:
            str or None: 批次ID，失败返回None
        """
        # 生成批次ID
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 构建批次数据
        batch = {
            "batch_id": batch_id,
            "status": "analyzed",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "priority": priority,
            "data": {
                "news_count": analysis_data.get("news_count", 0),
                "sentiment_score": analysis_data.get("sentiment_score", 0.5),
                "key_themes": analysis_data.get("key_themes", []),
                "ai_summary": analysis_data.get("ai_summary", ""),
                "alerts": analysis_data.get("alerts", []),
                "analysis_time": analysis_data.get("analysis_time", ""),
                "hotlist_count": analysis_data.get("hotlist_count", 0),
                "rss_count": analysis_data.get("rss_count", 0)
            }
        }
        
        # 获取锁并写入
        fd = self._acquire_lock()
        if fd is None:
            print(f"[QueueWriter] 获取锁超时")
            return None
        
        try:
            # 读取现有队列
            queue_data = self._read_queue()
            
            # 添加新批次
            queue_data["batches"].append(batch)
            queue_data["last_updated"] = datetime.now().isoformat()
            
            # 写入队列
            if self._write_queue(queue_data):
                print(f"[QueueWriter] 批次 {batch_id} 写入成功")
                return batch_id
            else:
                return None
        finally:
            self._release_lock(fd)
    
    def get_queue_status(self):
        """
        获取队列状态
        
        Returns:
            dict: 队列状态信息
        """
        queue_data = self._read_queue()
        batches = queue_data.get("batches", [])
        
        # 统计各状态批次数量
        status_count = {}
        for batch in batches:
            status = batch.get("status", "unknown")
            status_count[status] = status_count.get(status, 0) + 1
        
        return {
            "total_batches": len(batches),
            "status_count": status_count,
            "last_updated": queue_data.get("last_updated", "")
        }


def create_queue_dirs():
    """
    创建队列相关目录
    
    Returns:
        bool: 是否创建成功
    """
    dirs = [
        "/data/tasks",
        "/data/tasks/archive",
        "/data/results",
        "/data/knowledge",
        "/data/logs"
    ]
    
    for d in dirs:
        try:
            os.makedirs(d, exist_ok=True)
            print(f"[QueueWriter] 目录已创建: {d}")
        except Exception as e:
            print(f"[QueueWriter] 创建目录失败 {d}: {e}")
            return False
    
    # 初始化队列文件（如果不存在）
    queue_file = "/data/tasks/queue.json"
    if not os.path.exists(queue_file):
        try:
            with open(queue_file, 'w', encoding='utf-8') as f:
                json.dump({"version": "1.0", "last_updated": "", "batches": []}, f)
            print(f"[QueueWriter] 队列文件已初始化: {queue_file}")
        except Exception as e:
            print(f"[QueueWriter] 初始化队列文件失败: {e}")
            return False
    
    return True


if __name__ == '__main__':
    # 测试代码
    print("任务队列写入器测试")
    
    # 创建目录
    create_queue_dirs()
    
    # 测试写入
    writer = TaskQueueWriter()
    
    # 模拟分析数据
    test_data = {
        "news_count": 150,
        "sentiment_score": 0.65,
        "key_themes": ["央行降准", "半导体上涨", "新能源"],
        "ai_summary": "今日市场整体偏暖，央行降准释放流动性利好...",
        "alerts": [],
        "analysis_time": "2026-05-27 21:00:00",
        "hotlist_count": 100,
        "rss_count": 50
    }
    
    batch_id = writer.write_analysis_result(test_data, priority="high")
    print(f"写入批次ID: {batch_id}")
    
    # 查看队列状态
    status = writer.get_queue_status()
    print(f"队列状态: {status}")
