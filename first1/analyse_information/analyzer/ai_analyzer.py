import os
import json
import logging
import threading
import requests

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 3000
MAX_TOTAL_CONTENT_CHARS = 12000

UNIFIED_PROMPT = """你是一个面向嵌入式Linux/BSP/驱动开发者的信息分析助手。请对以下技术内容完成三个任务。

## 任务一：相关性评估（0-10分）
评分标准：
- 10分：直接相关（嵌入式Linux驱动开发、BSP移植、设备树配置等）
- 7-9分：高度相关（Linux内核、U-Boot、交叉编译工具链等）
- 4-6分：间接相关（通用Linux知识、编程技巧、硬件基础等）
- 1-3分：基本不相关（前端开发、Web后端、纯应用层开发等）
- 0分：完全不相关

{feedback_context}

## 任务二：结构化分析
如果相关性 >= 4 分，请按以下结构输出：

1. **一句话总结**：用一句简洁的话概括核心内容（不超过50字）
2. **三个关键点**：
   - 关键点1：最重要的信息
   - 关键点2：技术细节或背景
   - 关键点3：实际应用或影响
3. **对你的影响**：用第二人称说明这条信息对嵌入式Linux/BSP/驱动开发者具体有什么用，是否需要关注或采取行动
4. **难度等级**：入门/中级/高级
5. **行动建议**：推荐阅读/可选阅读/可以忽略

如果相关性 < 4 分，translation 字段填空字符串。

## 任务三：分类
从以下类别中选择最匹配的一个：
{categories}
如果相关性 < 4 分，category 字段填空字符串。

## 待分析内容
标题：{title}
内容：
{content}

## 输出要求
请只返回以下 JSON 格式，不要有其他内容：
{{"score": 分数, "reason": "简短理由", "translation": "结构化分析内容（包含一句话总结、三个关键点、对你的影响、难度等级、行动建议）", "category": "类别名称", "difficulty": "入门/中级/高级", "action": "推荐阅读/可选阅读/可以忽略"}}"""

RELEVANCE_KEYWORDS_PROMPT = """你是一个信息相关性评估专家。请判断以下技术内容是否与嵌入式Linux开发、BSP开发、设备驱动、RISC-V、IoT相关。

评分标准（0-10分）：
- 10分：直接相关（嵌入式Linux驱动开发、BSP移植、设备树配置等）
- 7-9分：高度相关（Linux内核、U-Boot、交叉编译工具链等）
- 4-6分：间接相关（通用Linux知识、编程技巧、硬件基础等）
- 1-3分：基本不相关（前端开发、Web后端、纯应用层开发等）
- 0分：完全不相关

技术内容标题：{title}
技术内容摘要：{summary}

请只返回一个JSON格式的结果，不要有其他内容：
{{"score": 分数, "reason": "简短理由"}}"""


def _smart_truncate(content: str, max_chars: int = MAX_CONTENT_CHARS) -> str:
    if len(content) <= max_chars:
        return content

    lines = content.split("\n")
    half = max_chars // 2

    head_lines = []
    head_len = 0
    for line in lines:
        if head_len + len(line) > half:
            break
        head_lines.append(line)
        head_len += len(line) + 1

    tail_lines = []
    tail_len = 0
    for line in reversed(lines):
        if tail_len + len(line) > half:
            break
        tail_lines.insert(0, line)
        tail_len += len(line) + 1

    return "\n".join(head_lines) + "\n\n[... 中间内容已省略 ...]\n\n" + "\n".join(tail_lines)


class TokenTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
        self.call_count = 0

    def record(self, usage: dict):
        with self._lock:
            self.total_prompt_tokens += usage.get("prompt_tokens", 0)
            self.total_completion_tokens += usage.get("completion_tokens", 0)
            self.total_tokens += usage.get("total_tokens", 0)
            self.call_count += 1

    def summary(self) -> dict:
        with self._lock:
            return {
                "call_count": self.call_count,
                "prompt_tokens": self.total_prompt_tokens,
                "completion_tokens": self.total_completion_tokens,
                "total_tokens": self.total_tokens,
                "estimated_cost_yuan": round(self.total_tokens * 0.002 / 1000, 4),
            }


class AIAnalyzer:
    def __init__(self, config: dict):
        self.config = config
        self.mimo_api_key = os.environ.get("MIMO_API_KEY", config.get("mimo_api_key", ""))
        self.mimo_api_base = config.get("mimo_api_base", "https://token-plan-cn.xiaomimimo.com/v1")
        self.mimo_model = config.get("mimo_model", "mimo-v2.5-pro")
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "") or self.mimo_api_key
        self.api_base = config.get("api_base", "https://token-plan-cn.xiaomimimo.com/v1")
        self.model = config.get("model", "mimo-v2.5-pro")
        self.max_tokens = config.get("max_tokens", 2000)
        self.temperature = config.get("temperature", 0.3)
        self.token_tracker = TokenTracker()
        self.max_calls = config.get("max_calls", 0)
        self.enable_deep_analysis = config.get("enable_deep_analysis_for_relevant", False)
        self.use_mimo = os.environ.get("USE_MIMO", "true").lower() == "true"

        if self.api_key.startswith("${"):
            env_key = self.api_key.strip("${}")
            self.api_key = os.environ.get(env_key, "")
        if self.mimo_api_key.startswith("${"):
            env_key = self.mimo_api_key.strip("${}")
            self.mimo_api_key = os.environ.get(env_key, "")

    def _call_api(self, prompt: str, max_tokens: int = None, use_mimo: bool = None) -> tuple:
        if use_mimo is None:
            use_mimo = self.use_mimo

        if self.max_calls > 0 and self.token_tracker.call_count >= self.max_calls:
            raise RuntimeError(f"已达到 API 调用上限 ({self.max_calls})")

        if use_mimo and self.mimo_api_key:
            api_key = self.mimo_api_key
            api_base = self.mimo_api_base
            model = self.mimo_model
        else:
            api_key = self.api_key
            api_base = self.api_base
            model = self.model

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": self.temperature,
        }

        try:
            resp = requests.post(
                f"{api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            self.token_tracker.record(usage)
            return content, usage
        except requests.exceptions.RequestException as e:
            logger.error("API 调用失败: %s", e)
            raise

    def _parse_json_response(self, raw: str) -> dict:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return json.loads(raw)

    def analyze_unified(self, title: str, content: str, config: dict, preferences: dict = None) -> dict:
        categories = config.get("categories", [])
        cat_list = "\n".join([f"- {c['name']}: {', '.join(c['keywords'])}" for c in categories])

        feedback_context = self._build_feedback_context(preferences)

        truncated = _smart_truncate(content, MAX_CONTENT_CHARS)

        prompt = UNIFIED_PROMPT.format(
            categories=cat_list,
            title=title,
            content=truncated,
            feedback_context=feedback_context,
        )

        if len(prompt) > MAX_TOTAL_CONTENT_CHARS:
            prompt = prompt[:MAX_TOTAL_CONTENT_CHARS]

        try:
            raw, usage = self._call_api(prompt, max_tokens=3000)
            parsed = self._parse_json_response(raw)

            score = float(parsed.get("score", 0))
            translation = parsed.get("translation", "")
            category = parsed.get("category", "")
            difficulty = parsed.get("difficulty", "")
            action = parsed.get("action", "")

            if score >= 6 and not translation:
                translation = self._fallback_translate(content)
            if score >= 6 and not category:
                category = self._categorize_by_keywords(content, categories)

            return {
                "relevant": score >= 6,
                "score": score,
                "reason": parsed.get("reason", ""),
                "translation": translation,
                "category": category,
                "difficulty": difficulty,
                "action": action,
                "token_usage": usage,
            }
        except Exception as e:
            logger.warning("统一分析失败，回退到分步模式: %s", e)
            return self._analyze_fallback(title, content, config)

    def _fallback_translate(self, content: str) -> str:
        truncated = _smart_truncate(content, 2000)
        prompt = f"请将以下技术内容翻译成大白话，用中文回答，Markdown格式：\n\n{truncated}"
        try:
            raw, _ = self._call_api(prompt)
            return raw
        except Exception:
            return ""

    def _analyze_fallback(self, title: str, content: str, config: dict) -> dict:
        relevance_config = config.get("relevance", {})
        keywords_config = relevance_config.get("keywords", {})
        categories = config.get("categories", [])

        all_keywords = self._flatten_keywords(keywords_config)

        keyword_score = 0
        for keyword in all_keywords:
            if keyword.lower() in content.lower():
                keyword_score += 1
        keyword_ratio = keyword_score / max(len(all_keywords), 1)

        if not self.api_key:
            weighted_score, best_cat = self._calculate_weighted_score(content, categories)
            final_score = max(round(keyword_ratio * 10, 1), weighted_score)
            return {
                "relevant": final_score >= 6,
                "score": final_score,
                "reason": f"基于关键词匹配 (命中 {keyword_score}/{len(all_keywords)})",
                "translation": "",
                "category": best_cat or self._categorize_by_keywords(content, categories),
                "token_usage": {},
            }

        try:
            summary = _smart_truncate(content, 500)
            prompt = RELEVANCE_KEYWORDS_PROMPT.format(title=title, summary=summary)
            raw, usage = self._call_api(prompt)
            parsed = self._parse_json_response(raw)
            ai_score = float(parsed.get("score", 0))

            weighted_score, best_cat = self._calculate_weighted_score(content, categories)
            final_score = max(ai_score, weighted_score)

            result = {
                "relevant": final_score >= 6,
                "score": final_score,
                "reason": parsed.get("reason", ""),
                "translation": "",
                "category": "",
                "token_usage": usage,
            }

            if final_score >= 6:
                result["translation"] = self._fallback_translate(content)
                result["category"] = best_cat or self._categorize_by_keywords(content, categories)

            return result
        except Exception as e:
            logger.warning("AI相关性判断失败，回退到关键词: %s", e)
            weighted_score, best_cat = self._calculate_weighted_score(content, categories)
            final_score = max(round(keyword_ratio * 10, 1), weighted_score)
            return {
                "relevant": final_score >= 6,
                "score": final_score,
                "reason": f"基于关键词匹配 (命中 {keyword_score}/{len(all_keywords)})",
                "translation": "",
                "category": best_cat or self._categorize_by_keywords(content, categories),
                "token_usage": {},
            }

    def _flatten_keywords(self, keywords_config) -> list:
        if isinstance(keywords_config, list):
            return keywords_config
        all_keywords = []
        if isinstance(keywords_config, dict):
            for group in keywords_config.values():
                if isinstance(group, list):
                    all_keywords.extend(group)
        return all_keywords

    def _calculate_weighted_score(self, content: str, categories: list) -> tuple:
        best_score = 0
        best_category = ""
        content_lower = content.lower()

        for cat in categories:
            name = cat.get("name", "")
            keywords = cat.get("keywords", [])
            weight = cat.get("weight", 0.5)

            match_count = sum(1 for kw in keywords if kw.lower() in content_lower)
            if match_count == 0:
                continue

            base_score = min(match_count / max(len(keywords), 1), 1.0) * 10
            weighted_score = round(base_score * weight, 1)

            if weighted_score > best_score:
                best_score = weighted_score
                best_category = name

        return best_score, best_category

    def _categorize_by_keywords(self, content: str, categories: list) -> str:
        best_cat = "00-收件箱"
        best_score = 0
        content_lower = content.lower()
        for cat in categories:
            score = sum(1 for kw in cat["keywords"] if kw.lower() in content_lower)
            if score > best_score:
                best_score = score
                best_cat = cat["name"]
        return best_cat

    def _build_feedback_context(self, preferences: dict = None) -> str:
        if not preferences:
            return ""

        parts = []

        liked = preferences.get("liked", [])
        if liked:
            parts.append("## 用户偏好参考（用户标记为「有用」的文章）：")
            for item in liked[:5]:
                parts.append(f"- ✅ [{item.get('category', '')}] {item.get('title', '')}")

        disliked = preferences.get("disliked", [])
        if disliked:
            parts.append("## 用户不喜欢的内容（用户标记为「没用」的文章）：")
            for item in disliked[:5]:
                parts.append(f"- ❌ [{item.get('category', '')}] {item.get('title', '')}")

        if parts:
            parts.append("")
            parts.append("请参考以上用户偏好来调整你的判断标准。用户喜欢的内容风格应该加分，不喜欢的应该减分。")

        return "\n".join(parts)

    def analyze(self, title: str, content: str, config: dict, preferences: dict = None) -> dict:
        return self.analyze_unified(title, content, config, preferences)

    def score_relevance(self, title: str, summary: str) -> dict:
        prompt = RELEVANCE_KEYWORDS_PROMPT.format(title=title, summary=summary[:2000])
        try:
            raw, _ = self._call_api(prompt, max_tokens=50, use_mimo=True)
            return self._parse_json_response(raw)
        except Exception as e:
            logger.warning("MiMo相关性评分失败: %s", e)
            return {"score": 5, "reason": "评分失败，默认中等"}

    def classify(self, title: str, content: str, categories: list) -> str:
        cat_list = ", ".join([c.get("name", "") for c in categories])
        prompt = f"将以下内容归入最合适的类别。可选类别：{cat_list}。只输出类别名称。\n\n标题：{title}\n内容：{content[:2000]}"
        try:
            raw, _ = self._call_api(prompt, max_tokens=20, use_mimo=True)
            return raw.strip()
        except Exception as e:
            logger.warning("MiMo分类失败: %s", e)
            return self._categorize_by_keywords(content, categories)

    def summarize(self, title: str, content: str) -> str:
        prompt = f"用一句话总结以下内容的核心要点，不超过50字。\n\n标题：{title}\n内容：{content[:3000]}"
        try:
            raw, _ = self._call_api(prompt, max_tokens=100, use_mimo=True)
            return raw.strip()
        except Exception as e:
            logger.warning("MiMo总结失败: %s", e)
            return ""
