# 百器模型 — 三层榫卯式 AI 架构设计

> 日期: 2026-06-04
> 状态: 待实施
> 关联: CLAUDE.md §15 训练模型与部署规划(v2)

## 1. 核心理念

**百器模型** = 小但精巧 + 榫卯结构 + 拼图式组合

- **大模型（DeepSeek）做"质"**：深度分析、策略推理、模式发现 — 每天处理 ~200 条精选内容
- **小模型（ONNX/LoRA）做"量"**：分类、筛选、排序、去重 — 每天处理 24 万条原始数据
- **榫卯扣合**：每层输出 = 下层输入，JSON Schema 精确契约，不依赖隐式上下文

### 设计原则

1. **每层只做一件事** — 哨兵只做分类预筛，LoRA 只做精细评分，DeepSeek 只做深度推理
2. **单层内独立部署** — 每层可在不同机器上独立运行，层间通过 JSON 契约通信
3. **降级友好** — 某层不可用时，自动跳过，不影响上下游
4. **逐层递减** — 第1层 5000→500，第2层 500→50，第3层只处理 50 条

## 2. 整体架构

```
TrendRadar 采集 (每30分钟, 5000条/次)
        │
        ▼
┌─────────────────────────────────────┐
│ 第1层 · 哨兵 (ONNX, CPU, <10ms/条)   │
│                                      │
│  S1-分类 → 新闻打标签 (科技/投资/综合) │
│  S2-情绪 → 预筛 (正/中/负)           │
│  S3-相关 → 粗筛预评分 (0.0-1.0)      │
│  S4-去重 → 语义去重                   │
│                                      │
│  输出: 5000条 → 500条 (筛选90%)       │
└──────────────┬──────────────────────┘
               │ JSON 契约
               ▼
┌─────────────────────────────────────┐
│ 第2层 · 榫卯 (Qwen1.5B + LoRA)       │
│    部署: 阿里云服务器 (7.1GB RAM)     │
│                                      │
│  LoRA-A → 精细相关评分 (0-10)        │
│  LoRA-C → 紧急度判断 (高/中/低)       │
│  (Phase2) LoRA-B → 细粒度情绪        │
│                                      │
│  输出: 500条 → 50条 (精选10%)         │
└──────────────┬──────────────────────┘
               │ JSON 契约
               ▼
┌─────────────────────────────────────┐
│ 第3层 · DeepSeek (顶层推理)           │
│                                      │
│  ① AI 热点分析 (5板块深度分析)        │
│  ② 每日简报 (事件→标志→代表)          │
│  ③ 投资策略建议                       │
│  ④ 模式识别 & 规则生成                │
│  ⑤ 个性化解读 (精简版)                │
│                                      │
│  每天处理: ~200 条                    │
│  每天成本: ~¥0.2                      │
└──────────────┬──────────────────────┘
               ▼
         钉钉推送 / invest
```

## 3. 接口契约（榫卯扣合点）

### 契约1: TrendRadar → 第1层哨兵

```json
{
  "title": "标题",
  "content": "摘要/正文前200字",
  "source": "微博",
  "platform_id": "weibo",
  "url": "https://...",
  "created_at": "2026-06-04T10:30:00Z"
}
```

### 契约2: 第1层 → 第2层

```json
{
  "title": "标题",
  "content": "摘要/正文前200字",
  "source": "微博",
  "platform_id": "weibo",
  "url": "https://...",
  "category": "科技",
  "sentiment_pre": "positive",
  "relevance_pre": 0.85,
  "dedup_group": "group_001"
}
```

### 契约3: 第2层 → 第3层

```json
{
  "title": "标题",
  "content": "摘要/正文前200字",
  "source": "微博",
  "platform_id": "weibo",
  "url": "https://...",
  "relevance": 0.92,
  "sentiment": {"label": "positive", "intensity": 0.78},
  "urgency": "high",
  "urgency_reason": "排名骤升: 15→3",
  "dedup_verified": true,
  "decision_factors": ["技术面:0.6", "情绪:0.3"]
}
```

## 4. 第1层 · 哨兵（ONNX 快筛层）

### 4.1 模型清单

| 模型 ID | 任务 | 基座 | 输出 | 标签 | 预计大小 |
|---------|------|------|------|------|---------|
| S1-category | 新闻分类 | DistilBERT | 4分类 | 科技/投资/综合/其他 | ~65MB |
| S2-sentiment | 情绪预筛 | DistilBERT | 3分类 | 正面/中性/负面 | ~65MB |
| S3-relevance | 相关预筛 | DistilBERT | 二分类 | 相关/不相关 + 分数 | ~65MB |
| S4-dedup | 语义去重 | MiniLM | 相似度 | 0-1 分数 | ~30MB |

### 4.2 训练管线

**训练脚本（已存在）：**
- `scripts/prepare_classifier_data.py` — 从 v2.2 合成数据提取训练集
- `scripts/train_news_classifier.py` — 训练 DistilBERT → ONNX 导出
- `scripts/classifier_server.py` — ONNX 推理服务（需改造支持多模型）

**训练数据来源：**
- 阿里云合成数据 v2.2 (127万条) — 用于 S1/S2/S3
- 需要新增: S4-dedup 的正负样本对构造脚本

**训练地点：** AutoDL (RTX 4090, 约 2-3 小时/每个模型)

### 4.3 部署方案

**部署位置：** 新加坡服务器 (188.166.249.182, 4GB/2核)

**格式：** ONNX + INT8 量化 (~30MB/模型, 4个约120MB)

**推理方式：** Python 进程内加载，与 TrendRadar 同进程运行

**集成点：** 修改 `__main__.py`，在 `_crawl_data()` 和 `_send_notification_if_needed()` 之间插入哨兵处理

```python
# 伪代码 — 集成位置
results, id_to_name, failed_ids = self._crawl_data()
# ── 第1层哨兵插入这里 ──
sentinel = Sentinel(models=["category", "sentiment", "relevance", "dedup"])
filtered = sentinel.process(results)
# ── 之后才进入推送逻辑 ──
self._execute_mode_strategy(mode_strategy, filtered, ...)
```

### 4.4 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `scripts/classifier_server.py` | ⚡ 改造 | 单模型→多模型管理器，支持 S1-S4 |
| `scripts/train_news_classifier.py` | ✅ 已存在 | 几乎不用改 |
| `scripts/prepare_classifier_data.py` | ⚡ 改造 | 新增 S4-dedup 数据提取 |
| `TrendRadar/trendradar/__main__.py` | ⚡ 改造 | 集成哨兵调用 |
| `TrendRadar/trendradar/core/loader.py` | ✅ 不涉及 | — |

## 5. 第2层 · 榫卯（Qwen1.5B + LoRA）

### 5.1 Phase 1 LoRA（P0, 必须做）

#### LoRA-A: 精细相关评分

| 项目 | 内容 |
|------|------|
| **任务** | 对新闻打分 0-10，衡量与用户关注点的匹配程度 |
| **输入** | 标题 + 摘要 + category + sentiment_pre |
| **输出** | `{"score": 8.5, "confidence": 0.92}` |
| **训练数据** | 从合成数据提取 100 万条（已有 `--task relevance` 管线） |
| **模型** | Qwen1.5B + LoRA (rank=16, alpha=32) |
| **训练时间** | AutoDL RTX 4090 约 3-4 小时 |
| **输出位置** | `models/loras/lora_a_relevance/` |

#### LoRA-C: 紧急度判断

| 项目 | 内容 |
|------|------|
| **任务** | 判断新闻是否需要立即关注 |
| **输入** | 标题 + 时间戳 + 热榜排名轨迹 + 平台 |
| **输出** | `{"level": "high", "reason": "排名骤升: 15→3"}` |
| **训练数据** | 从热榜历史数据构造 (排名变化 + 停留时长 + 跨平台扩散速度) |
| **标签定义** | high=紧急(排名骤升/跨平台爆发), medium=关注中, low=常规 |
| **训练时间** | AutoDL RTX 4090 约 2-3 小时 |
| **输出位置** | `models/loras/lora_c_urgency/` |

### 5.2 Phase 2 LoRA（P1, 后续加入）

#### LoRA-B: 细粒度情绪

| 项目 | 内容 |
|------|------|
| **任务** | 3分类 + 强度 (0-1) |
| **输入** | 标题 + 摘要 |
| **输出** | `{"label": "positive", "intensity": 0.78}` |
| **训练数据** | 合成数据 80 万条（已有 `--task sentiment` 管线） |
| **优先级** | P1 — 等 Phase 1 跑稳再加 |

### 5.3 LoRA 管理器

**文件:** `TrendRadar/scripts/lora_manager.py` (需新建)

```python
class LoraManager:
    """多 LoRA 切换管理器，按任务自动加载对应 adapter"""
    
    def __init__(self, base_model: str = "Qwen/Qwen1.5-1.5B"):
        self.base_model = base_model
        self.adapters = {}  # task_name -> peft_path
    
    def load_adapter(self, task: str) -> None:
        """加载指定任务的 LoRA adapter"""
    
    def infer(self, task: str, input_data: dict) -> dict:
        """按任务执行推理，自动切换 LoRA"""
    
    def unload_adapter(self, task: str) -> None:
        """卸载 adapter 释放内存"""
```

### 5.4 部署

**位置：** 阿里云服务器 (8.140.232.52, 7.1GB RAM, v3.0 生成器停产后使用)

**格式：** Qwen1.5B (GPTQ 量化 ~3GB) + LoRA adapter (~20MB/个)

**启动：** `python lora_server.py --port 5075` (提供 REST 接口)

**调用方式：** TrendRadar 通过 HTTP 调用阿里云 LoRA 服务

## 6. 第3层 · DeepSeek（顶层推理）

### 6.1 模型切换

把所有 MiMo 调用统一切到 DeepSeek：

| 配置项 | 旧值 | 新值 |
|--------|------|------|
| `ai.model` | `openai/mimo-v2.5-pro` | `deepseek/deepseek-chat` |
| `ai.api_key` | `${MIMO_API_KEY}` | `${DEEPSEEK_API_KEY}` |
| `ai.api_base` | `https://token-plan-cn.xiaomimimo.com/v1` | (空, 使用默认) |

### 6.2 保护机制

沿用已有的 `ai_gateway.py`（位于 `invest/scripts/`）：
- 日预算锁：`DEEPSEEK_DAILY_BUDGET_CNY=5.0`
- 输入超长锁：`DEEPSEEK_MAX_INPUT_CHARS=8000`
- 熔断锁：5次连续失败暂停15分钟

### 6.3 DeepSeek 独占任务

| 任务 | 触发频率 | 日均调用量 | 说明 |
|------|---------|-----------|------|
| AI 热点分析 (5板块) | 每次采集 | 48次 | 输入质量因前两层过滤大幅提升 |
| 每日简报 ("事件→标志→代表") | 9:00 | 1次 | 已实现 |
| 投资策略建议 | 每小时 | 24次 | 已存在 |
| 模式识别 & 规则生成 | 每天 | 1次 | Feedback 模块 |
| 个性化解读 (精简版) | 每次推送 | 4次 | 仅对 urgency=high 的新闻做 |

## 7. 实施路线图

### Phase 0: 配置迁移与基建（第1天）

- [x] 已完成：`SCHEDULED_PUSH` 配置加载修复
- [x] 已完成：AI 日报简报 prompt
- [ ] 修改 `config.yaml`: `ai.model` → `deepseek/deepseek-chat`
- [ ] 验证 DeepSeek 可用性

### Phase 1: 第1层哨兵上线（第1-2周）

| 任务 | 文件 | 时间 | 前提 |
|------|------|------|------|
| 1.1 准备 S1-S3 训练数据 | `prepare_classifier_data.py` (已有) | 第1天 | 阿里云数据可访问 |
| 1.2 准备 S4-dedup 数据 | 新增 `prepare_dedup_data.py` | 第1天 | 1.1 |
| 1.3 训练 S1-S4 | `train_news_classifier.py` (已有) | 第2-3天 | AutoDL |
| 1.4 改造 classifier_server | 支持多模型加载 | 第3天 | 1.3 模型就绪 |
| 1.5 集成到 TrendRadar | 修改 `__main__.py` | 第4-5天 | 1.4 |
| 1.6 部署到新加坡 | 拷贝模型+重启容器 | 第5天 | 1.5 |

### Phase 2: 第2层榫卯 Phase 1（第3-4周）

| 任务 | 文件 | 时间 | 前提 |
|------|------|------|------|
| 2.1 准备 LoRA-A 数据 | 已有 `--task relevance` 管线 | 第1天 | — |
| 2.2 准备 LoRA-C 数据 | 新增 `prepare_urgency_data.py` | 第2天 | 热榜历史数据 |
| 2.3 训练 LoRA-A 和 LoRA-C | `train_lora_heads.py` (新建) | 第3-4天 | AutoDL |
| 2.4 LoRA 管理器 | `lora_manager.py` (新建) | 第4-5天 | 2.3 |
| 2.5 阿里云部署接口 | `lora_server.py` (新建) | 第5-6天 | 2.4 |
| 2.6 影子模式验证 | `evaluate_shadow.py` (已有规划) | 第7天+ | 2.5 |

### Phase 3: 第2层榫卯 Phase 2 + 第3层调优（第5-6周）

| 任务 | 文件 | 时间 |
|------|------|------|
| 3.1 训练 LoRA-B | `train_lora_heads.py` | 第1-2天 |
| 3.2 减负 DeepSeek（验证无明显退化） | `evaluate_shadow.py` | 持续 |
| 3.3 调优 DeepSeek prompt（输入质量更高的适配） | `config/ai_analysis_prompt.txt` | 第3-5天 |

## 8. 成本收益分析

### 当前成本（全部用 MiMo/DeepSeek）

| 项目 | 日均调用量 | 单价 | 日均成本 |
|------|-----------|------|---------|
| AI 热点分析 | 48次 × ~2000 tokens | — | ~¥2-3 |
| 每日简报 | 4次 | — | ~¥0.05 |
| 其他 | ~50次 | — | ~¥0.5 |
| **合计** | | | **~¥3-4/天 (~¥100/月)** |

### 百器模型后成本

| 层 | 日均处理量 | 成本 |
|----|-----------|------|
| 第1层 ONNX | 24万条 | ¥0 |
| 第2层 LoRA | 2.4万条 | ¥0 |
| 第3层 DeepSeek | ~200条 | ~¥0.2/天 |
| **合计** | | **~¥0.2/天 (~¥6/月)** |

### 收益总结

- **API 成本降低 95%**：¥100/月 → ¥6/月
- **延迟降低**：DeepSeek 只处理 200 条，不再阻塞 Pipeline
- **覆盖量提升 20 倍**：第1层处理 24 万条/天（此前只能覆盖 2000 条/天）
- **推送质量提升**：经过四层筛选 + 紧急度判断，只推送真正重要的内容

## 9. 风险与降级

| 风险 | 影响 | 应对 |
|------|------|------|
| ONNX 模型精度不足 | 误筛或漏筛 | 低置信度回退到 DeepSeek；影子模式持续对比 |
| LoRA 服务器停机 | 第2层不可用 | 跳过第2层，第1层直接 → 第3层 |
| DeepSeek API 熔断 | 第3层不可用 | 第1层 → 第2层直接输出，推送"原始分类"替代深度分析 |
| 阿里云服务器重启 | LoRA 服务暂停 | supervisor 自动重启 + TrendRadar 侧超时跳过 |

## 10. 关键成功指标

| 指标 | 当前值 | 目标值 | 测量方式 |
|------|--------|--------|---------|
| API 月成本 | ~¥100 | <¥10 | 账单统计 |
| 每天 DeepSeek 调用量 | ~2000次 | <200次 | 日志统计 |
| 推送质量（用户留存） | 模糊 | 可量化 | 后续加反馈按钮 |
| 第1层分类准确率 | N/A | F1 > 0.90 | 测试集评估 |
| 第2层筛选率 | N/A | 10%（500→50） | 日志统计 |
