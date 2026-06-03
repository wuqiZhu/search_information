# -*- coding: utf-8 -*-
"""
决策透明度模块

让用户理解 AI 为什么做出某个投资建议。

功能：
1. 决策因子分解
2. 置信度计算
3. 风险提示生成
4. 可视化数据输出

使用方式:
    from shared.decision_transparency import DecisionExplainer

    explainer = DecisionExplainer()
    explanation = explainer.explain(decision)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class DecisionFactor:
    """决策因子"""
    name: str
    value: float  # 0-1
    weight: float  # 权重
    description: str
    evidence: List[str] = field(default_factory=list)


@dataclass
class RiskFactor:
    """风险因子"""
    name: str
    level: str  # high/medium/low
    probability: float  # 0-1
    impact: str
    mitigation: str


@dataclass
class Decision:
    """投资决策"""
    id: str
    timestamp: datetime = field(default_factory=datetime.now)

    # 决策内容
    action: str = ""  # buy/sell/hold
    target: str = ""  # 投资标的
    confidence: float = 0.0  # 置信度 0-1

    # 决策依据
    factors: List[DecisionFactor] = field(default_factory=list)
    risks: List[RiskFactor] = field(default_factory=list)

    # 原始数据
    raw_data: Dict[str, Any] = field(default_factory=dict)

    # 时间框架
    timeframe: str = "1-3个月"


@dataclass
class Explanation:
    """决策解释"""
    decision_id: str
    summary: str
    key_points: List[str]
    factor_breakdown: Dict[str, Any]
    risk_assessment: Dict[str, Any]
    confidence_analysis: Dict[str, Any]
    visualization_data: Dict[str, Any]


class DecisionExplainer:
    """决策解释器"""

    # 因子权重
    FACTOR_WEIGHTS = {
        "technical": 0.20,
        "sentiment": 0.15,
        "multi_timeframe": 0.15,
        "momentum": 0.15,
        "historical": 0.10,
        "volatility": 0.10,
        "market_sentiment": 0.10,
        "keywords": 0.05,
    }

    def explain(self, decision: Decision) -> Explanation:
        """生成决策解释"""
        # 1. 生成摘要
        summary = self._generate_summary(decision)

        # 2. 提取关键点
        key_points = self._extract_key_points(decision)

        # 3. 因子分解
        factor_breakdown = self._breakdown_factors(decision)

        # 4. 风险评估
        risk_assessment = self._assess_risks(decision)

        # 5. 置信度分析
        confidence_analysis = self._analyze_confidence(decision)

        # 6. 可视化数据
        visualization_data = self._prepare_visualization(decision)

        return Explanation(
            decision_id=decision.id,
            summary=summary,
            key_points=key_points,
            factor_breakdown=factor_breakdown,
            risk_assessment=risk_assessment,
            confidence_analysis=confidence_analysis,
            visualization_data=visualization_data,
        )

    def _generate_summary(self, decision: Decision) -> str:
        """生成决策摘要"""
        action_map = {
            "buy": "买入",
            "sell": "卖出",
            "hold": "持有",
            "increase": "加仓",
            "decrease": "减仓",
        }

        action_text = action_map.get(decision.action, decision.action)
        confidence_text = f"{decision.confidence:.0%}"

        if decision.confidence > 0.8:
            confidence_desc = "高度确信"
        elif decision.confidence > 0.6:
            confidence_desc = "较为确信"
        elif decision.confidence > 0.4:
            confidence_desc = "谨慎乐观"
        else:
            confidence_desc = "不确定性较高"

        summary = f"建议{action_text}{decision.target}，置信度{confidence_text}（{confidence_desc}）。"
        summary += f"时间框架：{decision.timeframe}。"

        return summary

    def _extract_key_points(self, decision: Decision) -> List[str]:
        """提取关键决策点"""
        key_points = []

        # 按权重排序因子
        sorted_factors = sorted(
            decision.factors,
            key=lambda f: f.weight * f.value,
            reverse=True,
        )

        # 提取前3个关键因子
        for factor in sorted_factors[:3]:
            if factor.value > 0.6:
                key_points.append(f"✅ {factor.description}")
            elif factor.value < 0.4:
                key_points.append(f"⚠️ {factor.description}")

        # 添加风险提示
        high_risks = [r for r in decision.risks if r.level == "high"]
        if high_risks:
            key_points.append(f"🔴 注意：存在{len(high_risks)}个高风险因素")

        return key_points

    def _breakdown_factors(self, decision: Decision) -> Dict[str, Any]:
        """因子分解"""
        breakdown = {
            "factors": [],
            "weighted_score": 0.0,
            "positive_factors": [],
            "negative_factors": [],
        }

        total_weighted_score = 0.0

        for factor in decision.factors:
            factor_info = {
                "name": factor.name,
                "value": factor.value,
                "weight": factor.weight,
                "weighted_value": factor.value * factor.weight,
                "description": factor.description,
                "evidence": factor.evidence,
            }

            breakdown["factors"].append(factor_info)
            total_weighted_score += factor.value * factor.weight

            if factor.value > 0.6:
                breakdown["positive_factors"].append(factor.name)
            elif factor.value < 0.4:
                breakdown["negative_factors"].append(factor.name)

        breakdown["weighted_score"] = total_weighted_score

        return breakdown

    def _assess_risks(self, decision: Decision) -> Dict[str, Any]:
        """风险评估"""
        assessment = {
            "overall_risk": "medium",
            "risks": [],
            "risk_score": 0.0,
            "mitigations": [],
        }

        if not decision.risks:
            assessment["overall_risk"] = "low"
            return assessment

        risk_scores = []
        for risk in decision.risks:
            risk_info = {
                "name": risk.name,
                "level": risk.level,
                "probability": risk.probability,
                "impact": risk.impact,
                "mitigation": risk.mitigation,
            }

            assessment["risks"].append(risk_info)
            risk_scores.append(risk.probability * {"high": 1.0, "medium": 0.6, "low": 0.3}.get(risk.level, 0.5))

            if risk.mitigation:
                assessment["mitigations"].append(risk.mitigation)

        # 计算总体风险分数
        if risk_scores:
            assessment["risk_score"] = sum(risk_scores) / len(risk_scores)

        # 确定总体风险等级
        if assessment["risk_score"] > 0.7:
            assessment["overall_risk"] = "high"
        elif assessment["risk_score"] > 0.4:
            assessment["overall_risk"] = "medium"
        else:
            assessment["overall_risk"] = "low"

        return assessment

    def _analyze_confidence(self, decision: Decision) -> Dict[str, Any]:
        """置信度分析"""
        analysis = {
            "confidence": decision.confidence,
            "level": "",
            "factors": [],
            "uncertainty_sources": [],
        }

        # 确定置信度等级
        if decision.confidence > 0.8:
            analysis["level"] = "高"
        elif decision.confidence > 0.6:
            analysis["level"] = "中高"
        elif decision.confidence > 0.4:
            analysis["level"] = "中"
        elif decision.confidence > 0.2:
            analysis["level"] = "中低"
        else:
            analysis["level"] = "低"

        # 分析影响置信度的因素
        for factor in decision.factors:
            if factor.value < 0.3:
                analysis["uncertainty_sources"].append(f"{factor.name}信号较弱")
            elif factor.value > 0.7:
                analysis["factors"].append(f"{factor.name}信号明确")

        return analysis

    def _prepare_visualization(self, decision: Decision) -> Dict[str, Any]:
        """准备可视化数据"""
        viz = {
            "radar_chart": {
                "labels": [],
                "values": [],
            },
            "factor_weights": {
                "labels": [],
                "values": [],
            },
            "risk_matrix": [],
        }

        # 雷达图数据
        for factor in decision.factors:
            viz["radar_chart"]["labels"].append(factor.name)
            viz["radar_chart"]["values"].append(factor.value)

        # 因子权重
        for factor in decision.factors:
            viz["factor_weights"]["labels"].append(factor.name)
            viz["factor_weights"]["values"].append(factor.weight)

        # 风险矩阵
        for risk in decision.risks:
            viz["risk_matrix"].append({
                "name": risk.name,
                "probability": risk.probability,
                "impact": {"high": 3, "medium": 2, "low": 1}.get(risk.level, 2),
            })

        return viz

    def generate_text_report(self, explanation: Explanation) -> str:
        """生成文本报告"""
        report = []
        report.append("=" * 60)
        report.append("投资决策分析报告")
        report.append("=" * 60)
        report.append("")

        # 摘要
        report.append("📋 决策摘要")
        report.append("-" * 40)
        report.append(explanation.summary)
        report.append("")

        # 关键点
        report.append("🎯 关键决策点")
        report.append("-" * 40)
        for point in explanation.key_points:
            report.append(f"  {point}")
        report.append("")

        # 因子分解
        report.append("📊 因子分解")
        report.append("-" * 40)
        for factor in explanation.factor_breakdown["factors"]:
            value_bar = "█" * int(factor["value"] * 10) + "░" * (10 - int(factor["value"] * 10))
            report.append(f"  {factor['name']}: {value_bar} {factor['value']:.0%}")
        report.append(f"  加权总分: {explanation.factor_breakdown['weighted_score']:.2f}")
        report.append("")

        # 风险评估
        report.append("⚠️ 风险评估")
        report.append("-" * 40)
        report.append(f"  总体风险: {explanation.risk_assessment['overall_risk']}")
        for risk in explanation.risk_assessment["risks"]:
            report.append(f"  - {risk['name']}: {risk['level']} ({risk['probability']:.0%})")
        report.append("")

        # 置信度
        report.append("📈 置信度分析")
        report.append("-" * 40)
        report.append(f"  置信度: {explanation.confidence_analysis['confidence']:.0%}")
        report.append(f"  等级: {explanation.confidence_analysis['level']}")
        report.append("")

        report.append("=" * 60)

        return "\n".join(report)


class DecisionBridge:
    """决策引擎与透明度模块的桥接器

    将 DecisionEngine 输出的 dict 转换为 Decision 对象，
    以便使用 DecisionExplainer 生成解释报告。
    """

    FACTOR_LABELS = {
        "sentiment_score": ("情绪面", 0.15),
        "technical_score": ("技术面", 0.20),
        "multi_timeframe_score": ("多时间框架", 0.15),
        "momentum_score": ("动量面", 0.15),
        "volatility_score": ("波动率", 0.10),
        "history_score": ("历史匹配", 0.10),
        "keyword_score": ("关键词", 0.05),
        "market_sentiment_score": ("市场情绪", 0.10),
    }

    ACTION_MAP = {"buy": "买入", "sell": "卖出", "hold": "持有"}

    @classmethod
    def from_engine_output(cls, engine_decision: Dict[str, Any]) -> Decision:
        """从 DecisionEngine.make_decision() 的输出构建 Decision 对象"""
        factors_data = engine_decision.get("factors", {})
        factors = []

        for key, (label, default_weight) in cls.FACTOR_LABELS.items():
            val = factors_data.get(key, 0.5)
            if isinstance(val, (int, float)):
                description = cls._describe_factor(key, val, factors_data)
                evidence = cls._collect_evidence(key, factors_data)
                factors.append(DecisionFactor(
                    name=label,
                    value=float(val),
                    weight=default_weight,
                    description=description,
                    evidence=evidence,
                ))

        # 风险因子
        risks = cls._build_risks(engine_decision)

        action = engine_decision.get("action", "hold")
        target = engine_decision.get("fund_name", engine_decision.get("fund_code", "未知"))

        return Decision(
            id=engine_decision.get("decision_id", "N/A"),
            timestamp=datetime.fromisoformat(engine_decision["timestamp"]) if "timestamp" in engine_decision else datetime.now(),
            action=action,
            target=target,
            confidence=engine_decision.get("confidence", 0.5),
            factors=factors,
            risks=risks,
            raw_data=engine_decision,
        )

    @classmethod
    def _describe_factor(cls, key: str, value: float, factors: Dict) -> str:
        """为因子生成可读描述"""
        if "sentiment" in key and "market" not in key:
            level = "偏多" if value > 0.6 else "偏空" if value < 0.4 else "中性"
            return f"市场情绪{level} ({value:.2f})"
        if "technical" in key:
            signal = factors.get("technical_signal", "N/A")
            return f"技术信号: {signal} ({value:.2f})"
        if "multi_timeframe" in key:
            signal = factors.get("multi_timeframe_signal", "N/A")
            return f"多时间框架信号: {signal} ({value:.2f})"
        if "momentum" in key:
            trend = "上行" if value > 0.6 else "下行" if value < 0.4 else "震荡"
            return f"动量{trend} ({value:.2f})"
        if "volatility" in key:
            level = "低波动" if value > 0.6 else "高波动" if value < 0.4 else "正常"
            return f"波动率{level} ({value:.2f})"
        if "history" in key:
            matched = factors.get("historical_match", False)
            return f"历史案例{'匹配' if matched else '未匹配'} ({value:.2f})"
        if "keyword" in key:
            return f"关键词评分 ({value:.2f})"
        if "market_sentiment" in key:
            level = factors.get("market_sentiment_level", "中性")
            idx = factors.get("market_sentiment_index", 50)
            return f"市场情绪指数: {level} ({idx:.0f})"
        return f"{key} = {value:.2f}"

    @classmethod
    def _collect_evidence(cls, key: str, factors: Dict) -> List[str]:
        """收集因子的证据"""
        evidence = []
        if "technical" in key:
            signal = factors.get("technical_signal")
            if signal:
                evidence.append(f"技术信号: {signal}")
        if "multi_timeframe" in key:
            signal = factors.get("multi_timeframe_signal")
            if signal and signal != "N/A":
                evidence.append(f"多时间框架: {signal}")
        if "market_sentiment" in key:
            level = factors.get("market_sentiment_level")
            if level:
                evidence.append(f"情绪等级: {level}")
        return evidence

    @classmethod
    def _build_risks(cls, engine_decision: Dict) -> List[RiskFactor]:
        """从引擎输出构建风险因子"""
        risks = []
        factors = engine_decision.get("factors", {})
        confidence = engine_decision.get("confidence", 0.5)

        # 低置信度风险
        if confidence < 0.5:
            risks.append(RiskFactor(
                name="置信度不足",
                level="high",
                probability=1 - confidence,
                impact="决策准确性较低",
                mitigation="建议减小仓位或观望",
            ))

        # 高波动风险
        vol = factors.get("volatility_score", 0.5)
        if vol < 0.4:
            risks.append(RiskFactor(
                name="高波动风险",
                level="medium",
                probability=0.6,
                impact="市场波动较大，短期回撤可能增加",
                mitigation="设置止损，控制仓位",
            ))

        # 动量反转风险
        momentum = factors.get("momentum_score", 0.5)
        if momentum > 0.7:
            risks.append(RiskFactor(
                name="追高风险",
                level="medium",
                probability=0.3,
                impact="动量过强，存在回调可能",
                mitigation="分批建仓，避免一次性投入",
            ))

        return risks


def explain_decision(decision: Decision) -> Explanation:
    """解释决策"""
    explainer = DecisionExplainer()
    return explainer.explain(decision)


def generate_decision_report(decision: Decision) -> str:
    """生成决策报告"""
    explainer = DecisionExplainer()
    explanation = explainer.explain(decision)
    return explainer.generate_text_report(explanation)


def explain_engine_decision(engine_decision: Dict[str, Any]) -> str:
    """一站式：从引擎输出直接生成文本报告"""
    decision = DecisionBridge.from_engine_output(engine_decision)
    return generate_decision_report(decision)


# 使用示例
if __name__ == "__main__":
    # 模拟 DecisionEngine 输出
    mock_engine_output = {
        "decision_id": "dec_20260603_120000_110011",
        "fund_code": "110011",
        "fund_name": "易方达中小盘",
        "action": "buy",
        "confidence": 0.72,
        "amount": 240,
        "reason": "情绪指数=0.72, 市场情绪=偏暖(65), 技术信号=BUY",
        "factors": {
            "sentiment_score": 0.72,
            "technical_score": 0.80,
            "technical_signal": "BUY",
            "multi_timeframe_score": 0.65,
            "multi_timeframe_signal": "偏多",
            "momentum_score": 0.70,
            "volatility_score": 0.55,
            "history_score": 0.60,
            "historical_match": True,
            "keyword_score": 0.65,
            "market_sentiment_index": 65,
            "market_sentiment_level": "偏暖",
            "market_sentiment_score": 0.65,
            "composite_score": 0.72,
        },
        "timestamp": "2026-06-03T12:00:00",
    }

    report = explain_engine_decision(mock_engine_output)
    print(report)
