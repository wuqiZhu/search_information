# -*- coding: utf-8 -*-
"""
消息队列模块

基于 Redis 的轻量级消息队列，用于服务间异步通信。

支持：
1. 点对点队列（Task Queue）
2. 发布订阅（Pub/Sub）
3. 延迟队列（Delayed Queue）
4. 死信队列（Dead Letter Queue）

使用方式:
    from shared.message_queue import get_queue

    queue = get_queue()

    # 发送消息
    await queue.publish("news_analysis", {"title": "...", "url": "..."})

    # 消费消息
    async for message in queue.subscribe("news_analysis"):
        await process(message)
        await message.ack()
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, AsyncIterator
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """消息对象"""
    id: str
    queue: str
    data: Any
    timestamp: float = field(default_factory=time.time)
    retry_count: int = 0
    max_retries: int = 3
    _acked: bool = False
    _nacked: bool = False

    def ack(self):
        """确认消息"""
        self._acked = True

    def nack(self, requeue: bool = True):
        """拒绝消息"""
        self._nacked = True

    @property
    def is_processed(self) -> bool:
        return self._acked or self._nacked

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "queue": self.queue,
            "data": self.data,
            "timestamp": self.timestamp,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        return cls(
            id=data["id"],
            queue=data["queue"],
            data=data["data"],
            timestamp=data.get("timestamp", time.time()),
            retry_count=data.get("retry_count", 0),
        )


class MemoryQueue:
    """内存消息队列（开发/测试用）"""

    def __init__(self):
        self.queues: Dict[str, asyncio.Queue] = {}
        self.subscribers: Dict[str, List[Callable]] = {}
        self.dead_letters: List[Message] = []

    async def publish(
        self,
        queue: str,
        data: Any,
        delay: float = 0,
        max_retries: int = 3,
    ) -> str:
        """发布消息"""
        import uuid

        message = Message(
            id=str(uuid.uuid4()),
            queue=queue,
            data=data,
            max_retries=max_retries,
        )

        if queue not in self.queues:
            self.queues[queue] = asyncio.Queue()

        if delay > 0:
            # 延迟消息
            asyncio.create_task(self._delayed_publish(message, delay))
        else:
            await self.queues[queue].put(message)

        # 通知订阅者
        if queue in self.subscribers:
            for callback in self.subscribers[queue]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(message)
                    else:
                        callback(message)
                except Exception as e:
                    logger.error(f"Subscriber callback error: {e}")

        logger.debug(f"Published message {message.id} to {queue}")
        return message.id

    async def _delayed_publish(self, message: Message, delay: float):
        """延迟发布"""
        await asyncio.sleep(delay)
        if message.queue not in self.queues:
            self.queues[message.queue] = asyncio.Queue()
        await self.queues[message.queue].put(message)

    async def consume(
        self,
        queue: str,
        timeout: float = None,
    ) -> Optional[Message]:
        """消费一条消息"""
        if queue not in self.queues:
            self.queues[queue] = asyncio.Queue()

        try:
            message = await asyncio.wait_for(
                self.queues[queue].get(),
                timeout=timeout,
            )
            return message
        except asyncio.TimeoutError:
            return None

    async def subscribe(self, queue: str) -> AsyncIterator[Message]:
        """订阅消息（异步迭代器）"""
        if queue not in self.queues:
            self.queues[queue] = asyncio.Queue()

        while True:
            message = await self.queues[queue].get()
            yield message

    def add_subscriber(self, queue: str, callback: Callable):
        """添加订阅者回调"""
        if queue not in self.subscribers:
            self.subscribers[queue] = []
        self.subscribers[queue].append(callback)

    async def handle_dead_letter(self, message: Message):
        """处理死信"""
        message.retry_count += 1
        if message.retry_count >= message.max_retries:
            self.dead_letters.append(message)
            logger.warning(f"Message {message.id} moved to dead letter queue")
        else:
            # 重新入队
            await self.queues[message.queue].put(message)
            logger.info(f"Message {message.id} requeued (retry {message.retry_count})")

    def get_queue_size(self, queue: str) -> int:
        """获取队列大小"""
        if queue not in self.queues:
            return 0
        return self.queues[queue].qsize()

    def get_dead_letters(self) -> List[Message]:
        """获取死信队列"""
        return self.dead_letters.copy()


class RedisQueue:
    """Redis 消息队列（生产环境用）"""

    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self.redis = None

    async def connect(self):
        """连接 Redis"""
        try:
            import redis.asyncio as aioredis
            self.redis = await aioredis.from_url(self.redis_url, decode_responses=True)
            logger.info(f"Connected to Redis: {self.redis_url}")
        except ImportError:
            logger.error("redis package not installed: pip install redis")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def disconnect(self):
        """断开连接"""
        if self.redis:
            await self.redis.close()

    async def publish(
        self,
        queue: str,
        data: Any,
        delay: float = 0,
        max_retries: int = 3,
    ) -> str:
        """发布消息"""
        import uuid

        message = Message(
            id=str(uuid.uuid4()),
            queue=queue,
            data=data,
            max_retries=max_retries,
        )

        if delay > 0:
            # 延迟队列
            execute_at = time.time() + delay
            await self.redis.zadd(
                f"delayed:{queue}",
                {json.dumps(message.to_dict()): execute_at}
            )
        else:
            # 普通队列
            await self.redis.rpush(
                f"queue:{queue}",
                json.dumps(message.to_dict())
            )

        # 发布通知
        await self.redis.publish(f"channel:{queue}", json.dumps(message.to_dict()))

        logger.debug(f"Published message {message.id} to {queue}")
        return message.id

    async def consume(
        self,
        queue: str,
        timeout: float = None,
    ) -> Optional[Message]:
        """消费一条消息"""
        # 先检查延迟队列
        await self._process_delayed(queue)

        # 从队列获取
        result = await self.redis.blpop(f"queue:{queue}", timeout=timeout or 0)
        if result:
            _, data = result
            message_data = json.loads(data)
            return Message.from_dict(message_data)

        return None

    async def _process_delayed(self, queue: str):
        """处理延迟队列"""
        now = time.time()
        delayed_key = f"delayed:{queue}"

        # 获取到期的消息
        messages = await self.redis.zrangebyscore(
            delayed_key, 0, now, start=0, num=100
        )

        for msg_data in messages:
            # 移动到普通队列
            await self.redis.rpush(f"queue:{queue}", msg_data)
            await self.redis.zrem(delayed_key, msg_data)

    async def subscribe(self, queue: str) -> AsyncIterator[Message]:
        """订阅消息"""
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(f"channel:{queue}")

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    yield Message.from_dict(data)
        finally:
            await pubsub.unsubscribe(f"channel:{queue}")

    async def handle_dead_letter(self, message: Message):
        """处理死信"""
        message.retry_count += 1
        if message.retry_count >= message.max_retries:
            await self.redis.rpush(
                f"dead_letter:{message.queue}",
                json.dumps(message.to_dict())
            )
            logger.warning(f"Message {message.id} moved to dead letter queue")
        else:
            await self.redis.rpush(
                f"queue:{message.queue}",
                json.dumps(message.to_dict())
            )
            logger.info(f"Message {message.id} requeued (retry {message.retry_count})")

    async def get_queue_size(self, queue: str) -> int:
        """获取队列大小"""
        return await self.redis.llen(f"queue:{queue}")

    async def get_dead_letters(self, queue: str) -> List[Message]:
        """获取死信队列"""
        messages = await self.redis.lrange(f"dead_letter:{queue}", 0, -1)
        return [Message.from_dict(json.loads(m)) for m in messages]


# 全局队列实例
_global_queue = None


def get_queue(redis_url: str = None) -> MemoryQueue:
    """获取全局队列实例"""
    global _global_queue

    if _global_queue is None:
        use_redis = os.environ.get("USE_REDIS", "false").lower() == "true"

        if use_redis:
            _global_queue = RedisQueue(redis_url)
        else:
            _global_queue = MemoryQueue()

    return _global_queue


async def init_queue():
    """初始化队列连接"""
    queue = get_queue()
    if isinstance(queue, RedisQueue):
        await queue.connect()
    return queue


async def close_queue():
    """关闭队列连接"""
    global _global_queue
    if _global_queue and isinstance(_global_queue, RedisQueue):
        await _global_queue.disconnect()
    _global_queue = None


# 使用示例
if __name__ == "__main__":
    async def example():
        queue = get_queue()

        # 发送消息
        msg_id = await queue.publish("test_queue", {"hello": "world"})
        print(f"Published: {msg_id}")

        # 消费消息
        message = await queue.consume("test_queue", timeout=5)
        if message:
            print(f"Consumed: {message.data}")
            message.ack()

    asyncio.run(example())
