# Search Information - 信息搜索与监控系统

## 项目概述

Search Information 是一个综合性的信息搜索与监控系统，集成了多个子项目，用于自动化收集、分析和推送各类信息。

## 项目结构

```
search_information/
├── TrendRadar/              # 热点新闻监控与推送系统
├── analyzer/                # 信息分析工具
├── n8n/                     # 自动化工作流
├── bestblogs/               # 博客内容聚合
├── onelllm/                 # 统一LLM接口
├── .env.example             # 环境变量配置模板
├── start.bat                # Windows启动脚本
├── start.sh                 # Linux/Mac启动脚本
└── README.md                # 本文件
```

## 子项目介绍

### 1. TrendRadar
热点新闻监控与推送系统，支持多平台数据抓取和多种推送渠道。

**功能特点：**
- 全网热点聚合（知乎、抖音、B站等）
- 智能关键词筛选
- 多渠道推送（微信、飞书、钉钉、Telegram等）
- 定时任务调度
- AI分析功能

### 2. Analyzer
信息分析工具，用于对收集到的信息进行深度分析和处理。

### 3. n8n
自动化工作流引擎，用于连接各种服务和API。

### 4. BestBlogs
博客内容聚合系统，用于收集和整理优质博客内容。

### 5. OneLLM
统一LLM接口，简化与各种大语言模型的交互。

## 快速开始

### 环境要求
- Python 3.8+
- Node.js 16+（用于n8n和前端项目）
- Git

### 安装步骤

1. 克隆项目
```bash
git clone https://github.com/yourusername/search_information.git
cd search_information
```

2. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 文件，填入你的配置
```

3. 启动服务
```bash
# Windows
start.bat

# Linux/Mac
chmod +x start.sh
./start.sh
```

## 配置说明

### 环境变量
所有敏感配置都通过环境变量管理，请参考 `.env.example` 文件。

### 子项目配置
各子项目有独立的配置文件，请参考各子项目的README文档。

## 注意事项

1. **安全性**：请勿将 `.env` 文件提交到Git仓库
2. **隐私保护**：个人配置文件（如 `profile.json`）已被 `.gitignore` 排除
3. **依赖管理**：各子项目有独立的依赖管理，请分别安装

## 许可证

本项目采用 MIT 许可证，详见各子项目的LICENSE文件。

## 联系方式

如有问题或建议，请通过GitHub Issues反馈。