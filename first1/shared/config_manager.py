# -*- coding: utf-8 -*-
"""
统一配置管理模块

集中管理所有子项目的配置，支持：
1. 环境变量覆盖
2. 配置文件加载
3. 配置验证
4. 敏感信息脱敏

使用方式:
    from shared.config_manager import get_config

    config = get_config()
    api_key = config.ai.api_key
    db_path = config.database.trendradar_path
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class AIConfig:
    """AI 模型配置"""
    # MiMo API
    mimo_api_key: str = ""
    mimo_api_url: str = "https://api.mimo.ai/v1"
    mimo_model: str = "mimo-v2.5-pro"

    # DeepSeek API
    deepseek_api_key: str = ""
    deepseek_api_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # 缓存配置
    cache_enabled: bool = True
    cache_dir: str = "/tmp/ai_cache"
    cache_max_age_days: int = 30
    cache_max_size_mb: int = 500

    # 限流配置
    rate_limit_per_minute: int = 60
    rate_limit_per_day: int = 10000

    def get_api_keys(self, provider: str = "mimo") -> List[str]:
        """获取 API 密钥列表（支持多密钥轮询）"""
        if provider == "mimo":
            keys_str = os.environ.get("MIMO_API_KEYS", self.mimo_api_key)
        elif provider == "deepseek":
            keys_str = os.environ.get("DEEPSEEK_API_KEYS", self.deepseek_api_key)
        else:
            return []

        return [k.strip() for k in keys_str.split(",") if k.strip()]


@dataclass
class DatabaseConfig:
    """数据库配置"""
    # 基础路径
    data_base: str = "/app/data"

    # TrendRadar 热榜数据库（按日期分库）
    trendradar_dir: str = "search_information/news"

    # RSS 数据库（按日期分库）
    rss_dir: str = "search_information/rss"

    # 分析数据库
    analyse_db: str = "knowledge_base/analyzer.db"

    # 投资数据库
    invest_db: str = "invest/fund_data.db"

    # 反馈数据库
    feedback_db: str = "invest/feedback.db"

    @property
    def trendradar_path(self) -> str:
        """获取最新的热榜数据库路径"""
        return self._find_latest_db(self.trendradar_dir)

    @property
    def rss_path(self) -> str:
        """获取最新的 RSS 数据库路径"""
        return self._find_latest_db(self.rss_dir)

    @property
    def analyse_path(self) -> str:
        return str(Path(self.data_base) / self.analyse_db)

    @property
    def invest_path(self) -> str:
        return str(Path(self.data_base) / self.invest_db)

    @property
    def feedback_path(self) -> str:
        return str(Path(self.data_base) / self.feedback_db)

    def _find_latest_db(self, subdir: str) -> str:
        """查找最新的数据库文件"""
        db_dir = Path(self.data_base) / subdir
        if not db_dir.exists():
            return ""

        db_files = sorted(db_dir.glob("*.db"), reverse=True)
        return str(db_files[0]) if db_files else ""


@dataclass
class ServerConfig:
    """服务器配置"""
    # 新加坡服务器
    singapore_host: str = "188.166.249.182"
    singapore_user: str = "root"

    # 阿里云服务器
    aliyun_host: str = "8.140.232.52"
    aliyun_user: str = "root"

    # Dashboard 服务
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8085
    dashboard_auth_token: str = ""

    # 语义搜索服务
    semantic_search_host: str = "0.0.0.0"
    semantic_search_port: int = 5070

    # 投资后端服务
    invest_backend_host: str = "0.0.0.0"
    invest_backend_port: int = 5000

    # 投资前端服务
    invest_frontend_port: int = 3000

    # 通知中心服务
    notification_host: str = "0.0.0.0"
    notification_port: int = 5050


@dataclass
class NotificationConfig:
    """通知配置"""
    # 钉钉
    dingtalk_enabled: bool = True
    dingtalk_webhook: str = ""
    dingtalk_secret: str = ""

    # 企业微信
    wechat_enabled: bool = False
    wechat_webhook: str = ""

    # Telegram
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""


@dataclass
class AppConfig:
    """应用总配置"""
    ai: AIConfig = field(default_factory=AIConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)

    # 环境
    env: str = "production"  # production / development / testing
    debug: bool = False
    log_level: str = "INFO"

    def load_from_env(self):
        """从环境变量加载配置"""
        # 环境
        self.env = os.environ.get("APP_ENV", self.env)
        self.debug = os.environ.get("APP_DEBUG", "false").lower() == "true"
        self.log_level = os.environ.get("LOG_LEVEL", self.log_level)

        # AI 配置
        self.ai.mimo_api_key = os.environ.get("MIMO_API_KEY", self.ai.mimo_api_key)
        self.ai.mimo_api_url = os.environ.get("MIMO_API_URL", self.ai.mimo_api_url)
        self.ai.deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY", self.ai.deepseek_api_key)
        self.ai.cache_enabled = os.environ.get("AI_CACHE_ENABLED", "true").lower() == "true"
        self.ai.cache_dir = os.environ.get("AI_CACHE_DIR", self.ai.cache_dir)

        # 数据库配置
        self.database.data_base = os.environ.get("DATA_BASE", self.database.data_base)

        # 服务器配置
        self.server.dashboard_auth_token = os.environ.get("DASHBOARD_AUTH_TOKEN", self.server.dashboard_auth_token)
        self.server.dashboard_port = int(os.environ.get("DASHBOARD_PORT", str(self.server.dashboard_port)))

        # 通知配置
        self.notification.dingtalk_webhook = os.environ.get("DINGTALK_WEBHOOK", self.notification.dingtalk_webhook)
        self.notification.dingtalk_secret = os.environ.get("DINGTALK_SECRET", self.notification.dingtalk_secret)

    def load_from_file(self, config_path: str):
        """从 YAML 配置文件加载"""
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)

            if config_data:
                self._update_from_dict(config_data)
        except ImportError:
            pass  # PyYAML 未安装，跳过
        except Exception as e:
            pass  # 配置文件读取失败

    def _update_from_dict(self, data: Dict[str, Any], prefix: str = ""):
        """从字典更新配置"""
        for key, value in data.items():
            attr_name = f"{prefix}{key}" if prefix else key

            if hasattr(self, attr_name):
                attr = getattr(self, attr_name)
                if isinstance(attr, (AIConfig, DatabaseConfig, ServerConfig, NotificationConfig)):
                    # 递归更新子配置
                    if isinstance(value, dict):
                        for sub_key, sub_value in value.items():
                            if hasattr(attr, sub_key):
                                setattr(attr, sub_key, sub_value)
                else:
                    setattr(self, attr_name, value)

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典（脱敏敏感信息）"""
        def mask_sensitive(value: str) -> str:
            """脱敏敏感信息"""
            if not value or len(value) < 8:
                return "***"
            return value[:4] + "***" + value[-4:]

        return {
            "env": self.env,
            "debug": self.debug,
            "log_level": self.log_level,
            "ai": {
                "mimo_api_key": mask_sensitive(self.ai.mimo_api_key),
                "mimo_model": self.ai.mimo_model,
                "cache_enabled": self.ai.cache_enabled,
                "cache_dir": self.ai.cache_dir,
            },
            "database": {
                "data_base": self.database.data_base,
                "trendradar_path": self.database.trendradar_path,
                "rss_path": self.database.rss_path,
            },
            "server": {
                "dashboard_port": self.server.dashboard_port,
                "dashboard_auth_enabled": bool(self.server.dashboard_auth_token),
            },
            "notification": {
                "dingtalk_enabled": self.notification.dingtalk_enabled,
                "wechat_enabled": self.notification.wechat_enabled,
            },
        }


# 全局配置实例
_global_config: Optional[AppConfig] = None


def get_config(
    config_file: str = None,
    load_env: bool = True,
) -> AppConfig:
    """
    获取全局配置实例

    Args:
        config_file: 配置文件路径
        load_env: 是否从环境变量加载

    Returns:
        AppConfig 实例
    """
    global _global_config

    if _global_config is None:
        _global_config = AppConfig()

        # 从环境变量加载
        if load_env:
            _global_config.load_from_env()

        # 从配置文件加载
        if config_file:
            _global_config.load_from_file(config_file)

    return _global_config


def reset_config():
    """重置全局配置（用于测试）"""
    global _global_config
    _global_config = None


# 使用示例
if __name__ == "__main__":
    # 获取配置
    config = get_config()

    # 打印配置（脱敏）
    import json
    print(json.dumps(config.to_dict(), indent=2, ensure_ascii=False))

    # 访问具体配置
    print(f"\nAI 缓存启用: {config.ai.cache_enabled}")
    print(f"数据库路径: {config.database.data_base}")
    print(f"Dashboard 端口: {config.server.dashboard_port}")
