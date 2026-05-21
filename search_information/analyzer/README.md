# 信息分析器

将技术信息翻译成大白话，筛选与你相关的内容，沉淀到 Obsidian 知识库。

## 功能

- **内容提取**：使用 Defuddle 提取网页干净正文
- **AI 分析**：使用 DeepSeek API 进行内容分析
- **大白话翻译**：将技术内容翻译成普通人能理解的语言
- **相关性筛选**：自动筛选与你相关的内容
- **知识沉淀**：保存到 Obsidian 知识库

## 使用方法

### 分析单个 URL

```bash
cd analyzer/scripts
python analyze.py https://example.com/article
```

### 处理信号文件

```bash
cd analyzer/scripts
python analyze.py --signals ../trendradar/data/signals/xxx.json
```

### 单独提取内容

```bash
cd analyzer/scripts
python extract_content.py https://example.com/article
```

### 单独分析内容

```bash
cd analyzer/scripts
python ai_analyze.py ../knowledge_base/raw/xxx.json
```

## 目录结构

```
analyzer/
├── config.yaml          # 配置文件
├── scripts/             # 脚本目录
│   ├── analyze.py       # 主分析脚本
│   ├── extract_content.py  # 内容提取
│   └── ai_analyze.py    # AI 分析
└── README.md            # 说明文档

knowledge_base/
├── raw/                 # 原始内容
├── analyzed/            # 分析后内容
├── translated/          # 大白话翻译
└── obsidian/            # Obsidian 笔记
    ├── 00-收件箱/       # 新采集的内容
    ├── 01-嵌入式Linux/  # 分类整理
    ├── 02-BSP开发/
    ├── 03-设备驱动/
    ├── 04-RISC-V/
    ├── 05-IoT/
    └── templates/       # 笔记模板
```

## 配置说明

编辑 `config.yaml` 文件：

- **relevance.keywords**：与你相关的关键词
- **relevance.min_score**：最小相关性评分（0-1）
- **categories**：内容分类规则
- **ai.api_key**：DeepSeek API Key

## 与 TrendRadar 集成

TrendRadar 检测到信号后，可以调用分析器进行深度分析：

```bash
# 处理 TrendRadar 的信号
cd analyzer/scripts
python analyze.py --signals ../../trendradar/data/signals/xxx.json
```

## 注意事项

1. 需要安装 Defuddle：`npm install -g defuddle`
2. 需要配置 DeepSeek API Key
3. 首次运行会创建 Obsidian 知识库目录结构
