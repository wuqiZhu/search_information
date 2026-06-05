# -*- coding: utf-8 -*-
"""
配置管理模块测试
"""

import os
import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config_manager import AppConfig, get_config, reset_config


@pytest.fixture
def clean_env():
    """清理环境变量"""
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)


class TestAppConfig:
    """应用配置测试"""

    def test_default_values(self):
        """测试默认值"""
        config = AppConfig()

        assert config.env == "production"
        assert config.debug is False
        assert config.log_level == "INFO"
        assert config.ai.cache_enabled is True
        assert config.server.dashboard_port == 8085

    def test_load_from_env(self, clean_env):
        """测试从环境变量加载"""
        os.environ["APP_ENV"] = "development"
        os.environ["APP_DEBUG"] = "true"
        os.environ["LOG_LEVEL"] = "DEBUG"
        os.environ["DASHBOARD_PORT"] = "9090"

        config = AppConfig()
        config.load_from_env()

        assert config.env == "development"
        assert config.debug is True
        assert config.log_level == "DEBUG"
        assert config.server.dashboard_port == 9090

    def test_ai_config(self, clean_env):
        """测试 AI 配置"""
        os.environ["MIMO_API_KEY"] = "test-key-123"
        os.environ["AI_CACHE_ENABLED"] = "false"

        config = AppConfig()
        config.load_from_env()

        assert config.ai.mimo_api_key == "test-key-123"
        assert config.ai.cache_enabled is False

    def test_notification_config(self, clean_env):
        """测试通知配置"""
        os.environ["DINGTALK_WEBHOOK"] = "https://test.webhook"
        os.environ["DINGTALK_SECRET"] = "test-secret"

        config = AppConfig()
        config.load_from_env()

        assert config.notification.dingtalk_webhook == "https://test.webhook"
        assert config.notification.dingtalk_secret == "test-secret"

    def test_to_dict_masking(self):
        """测试敏感信息脱敏"""
        config = AppConfig()
        config.ai.mimo_api_key = "abcdefghijklmnop"

        result = config.to_dict()

        assert result["ai"]["mimo_api_key"] == "abcd***mnop"
        assert "***" in result["ai"]["mimo_api_key"]

    def test_to_dict_short_key(self):
        """测试短密钥脱敏"""
        config = AppConfig()
        config.ai.mimo_api_key = "short"

        result = config.to_dict()

        assert result["ai"]["mimo_api_key"] == "***"

    def test_database_config(self, clean_env):
        """测试数据库配置"""
        os.environ["DATA_BASE"] = "/custom/data"

        config = AppConfig()
        config.load_from_env()

        assert config.database.data_base == "/custom/data"

    def test_server_config(self):
        """测试服务器配置"""
        config = AppConfig()

        assert config.server.singapore_host == "188.166.249.182"
        assert config.server.aliyun_host == "8.140.232.52"

    def test_api_keys(self, clean_env):
        """测试 API 密钥列表"""
        os.environ["MIMO_API_KEYS"] = "key1,key2,key3"

        config = AppConfig()
        config.load_from_env()

        keys = config.ai.get_api_keys("mimo")
        assert len(keys) == 3
        assert "key1" in keys


class TestGlobalConfig:
    """全局配置测试"""

    def test_singleton(self):
        """测试单例模式"""
        reset_config()
        config1 = get_config()
        config2 = get_config()

        assert config1 is config2

    def test_reset(self):
        """测试重置"""
        reset_config()
        config1 = get_config()
        reset_config()
        config2 = get_config()

        assert config1 is not config2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
