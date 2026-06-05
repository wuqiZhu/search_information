#!/usr/bin/env python3
"""
统计预测模块 — 基于情绪指数 + 基金净值 + 新闻量的趋势推演

不需要模型，不需要 GPU，纯统计方法：
  - 情绪动量：短期均值 vs 中期均值的偏离
  - 趋势加速度：斜率变化
  - 波动率：最近 N 天的标准差
  - 新闻热度：新闻量的相对变化

用法:
  python3 predictor.py                 → 完整预测报告
  python3 predictor.py --sentiment     → 只看情绪预测
  python3 predictor.py --brief         → 一句话预测（供 briefing_push.py 用）
"""

import json
import math
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path


def load_sentiment_history(days=30):
    """加载情绪指数历史"""
    path = "/root/projects/data/invest/sentiment/sentiment_history.json"
    if not os.path.exists(path):
        return []
    with open(path) as f:
        data = json.load(f)
    return data[-days:]


def load_fund_nav(days=30):
    """加载基金净值变化率"""
    path = "/root/projects/data/invest/fund_data.db"
    if not os.path.exists(path):
        return []
    try:
        conn = sqlite3.connect(path)
        rows = conn.execute(
            "SELECT nav_date, daily_return FROM fund_nav WHERE daily_return IS NOT NULL ORDER BY nav_date DESC LIMIT ?",
            (days * 3,)  # 多取一些因为有多只基金
        ).fetchall()
        conn.close()
        # 按日期聚合取平均
        daily_returns = {}
        for date, ret in rows:
            if ret is None:
                continue
            d = date[:10] if len(date) >= 10 else date
            if d not in daily_returns:
                daily_returns[d] = []
            daily_returns[d].append(float(ret))
        result = []
        for date in sorted(daily_returns.keys())[-days:]:
            vals = daily_returns[date]
            if vals:
                result.append({"date": date, "avg_return": sum(vals) / len(vals)})
        return result
    except Exception:
        return []


def load_news_volume(days=7):
    """加载每天新闻量"""
    news_dir = "/root/projects/data/search_information/news"
    if not os.path.exists(news_dir):
        return []
    dbs = sorted([f for f in os.listdir(news_dir) if f.endswith(".db")])
    result = []
    for db_name in dbs[-days:]:
        try:
            conn = sqlite3.connect(os.path.join(news_dir, db_name))
            count = conn.execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
            conn.close()
            result.append({"date": db_name.replace(".db", ""), "count": count})
        except:
            pass
    return result


def moving_average(values, window):
    """移动平均"""
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def slope(values):
    """线性回归斜率（简化版）"""
    n = len(values)
    if n < 2:
        return 0
    x_avg = (n - 1) / 2
    y_avg = sum(values) / n
    num = sum((i - x_avg) * (v - y_avg) for i, v in enumerate(values))
    den = sum((i - x_avg) ** 2 for i in range(n))
    return num / den if den != 0 else 0


def standard_deviation(values):
    """标准差"""
    n = len(values)
    if n < 2:
        return 0
    avg = sum(values) / n
    variance = sum((v - avg) ** 2 for v in values) / (n - 1)
    return math.sqrt(variance)


def predict_sentiment(history):
    """情绪指数预测"""
    if len(history) < 7:
        return {"latest": history[-1]["index"] if history else 0, "direction": "unknown",
                "confidence": 0, "range_3d": "?", "signal": "数据不足（需7天以上）",
                "momentum": 0, "acceleration": 0, "volatility": 0,
                "ma_3": None, "ma_7": None, "score": 0}

    values = [h.get("index", 50) for h in history]

    # 关键指标
    ma_3 = moving_average(values, 3)      # 短期均线
    ma_7 = moving_average(values, 7)      # 中期均线
    ma_14 = moving_average(values, 14)    # 长期均线
    latest = values[-1]

    # 情绪动量 = 短期 - 中期（正=上行趋势）
    momentum = (ma_3 - ma_7) if ma_3 and ma_7 else 0

    # 趋势加速度 = 近3天斜率 vs 近7天斜率
    s_3 = slope(values[-3:]) if len(values) >= 3 else 0
    s_7 = slope(values[-7:]) if len(values) >= 7 else 0
    acceleration = s_3 - s_7

    # 波动率
    vol = standard_deviation(values[-7:])

    # 极值检测
    near_min = latest <= min(values[-14:]) + vol if len(values) >= 14 else False
    near_max = latest >= max(values[-14:]) - vol if len(values) >= 14 else False

    # 方向判断
    if momentum > vol * 0.5:
        direction = "up"
        signal = "情绪正在回暖"
    elif momentum < -vol * 0.5:
        direction = "down"
        signal = "情绪持续走弱"
    else:
        direction = "sideways"
        signal = "情绪震荡整理"

    # 置信度
    confidence = min(abs(momentum) / max(vol, 1), 1.0)
    confidence = max(confidence, 0.1)

    # 极端情况修正
    if near_min and direction == "down":
        direction = "reversal_up"
        signal = "超卖区域，可能反弹"
        confidence = min(confidence + 0.2, 0.8)
    elif near_max and direction == "up":
        direction = "reversal_down"
        signal = "超买区域，可能回调"
        confidence = min(confidence + 0.2, 0.8)

    # 预测区间
    pred_low = max(0, round(latest - vol * 1.5, 1))
    pred_high = min(100, round(latest + vol * 1.5, 1))

    # 加权综合评分（-100 ~ +100）
    score = momentum * 10 + acceleration * 5
    if direction in ("up", "reversal_up"):
        score = abs(score)
    elif direction in ("down", "reversal_down"):
        score = -abs(score)

    return {
        "latest": latest,
        "direction": direction,
        "signal": signal,
        "confidence": round(confidence, 2),
        "range_3d": f"{pred_low}~{pred_high}",
        "momentum": round(momentum, 2),
        "acceleration": round(acceleration, 2),
        "volatility": round(vol, 2),
        "ma_3": round(ma_3, 1) if ma_3 else None,
        "ma_7": round(ma_7, 1) if ma_7 else None,
        "score": round(score, 1),
    }


def predict_market(fund_nav_data):
    """市场走势预测（基于基金净值）"""
    if not fund_nav_data or len(fund_nav_data) < 5:
        return {"direction": "unknown", "confidence": 0}

    returns = [d["avg_return"] for d in fund_nav_data]

    # 最近平均收益率
    r_3 = moving_average(returns, 3) or 0
    r_7 = moving_average(returns, 7) or 0

    # 收益率动量
    momentum = r_3 - r_7

    # 波动率
    vol = standard_deviation(returns)

    if momentum > vol * 0.3:
        direction = "up"
    elif momentum < -vol * 0.3:
        direction = "down"
    else:
        direction = "sideways"

    confidence = min(abs(momentum) / max(vol, 0.01), 1.0)

    return {
        "direction": direction,
        "confidence": round(confidence, 2),
        "avg_return_3d": round(r_3, 4),
        "avg_return_7d": round(r_7, 4),
        "volatility": round(vol, 4),
    }


def predict_news_heat(news_volume):
    """新闻热度预测"""
    if not news_volume or len(news_volume) < 3:
        return {"trend": "unknown"}

    counts = [d["count"] for d in news_volume]
    recent_3 = moving_average(counts, 3) or 0
    earlier = moving_average(counts[:-3], 3) if len(counts) >= 6 else 0

    if earlier == 0:
        return {"trend": "stable", "ratio": 1.0}

    ratio = recent_3 / earlier

    if ratio > 1.3:
        trend = "rising"
    elif ratio < 0.7:
        trend = "falling"
    else:
        trend = "stable"

    return {
        "trend": trend,
        "ratio": round(ratio, 2),
        "avg_daily_3d": round(recent_3),
        "avg_daily_earlier": round(earlier) if earlier else 0,
    }


def generate_summary(sentiment_pred, market_pred, news_pred):
    """生成一句话总结+建议"""
    s_dir = sentiment_pred.get("direction", "unknown")
    s_signal = sentiment_pred.get("signal", "")
    s_conf = sentiment_pred.get("confidence", 0)
    s_range = sentiment_pred.get("range_3d", "?")

    # 综合得分
    score = sentiment_pred.get("score", 0)

    if s_dir == "unknown":
        return {"brief": "数据不足，暂无法预测", "suggestion": "⏳ 持续积累数据中...",
                "score": 0, "direction_emoji": "❓", "confidence_label": "低", "predicted_range": "?"}

    dir_map = {
        "up": "📈 看涨", "down": "📉 看跌", "sideways": "➡️ 震荡",
        "reversal_up": "↗️ 反弹", "reversal_down": "↘️ 回调", "unknown": "❓ 不明",
    }
    dir_str = dir_map.get(s_dir, s_dir)

    # 置信度映射
    if s_conf >= 0.6:
        conf_str = "高"
    elif s_conf >= 0.3:
        conf_str = "中"
    else:
        conf_str = "低"

    brief = f"{dir_str} | 置信度{conf_str} | 未来3天区间 {s_range} | {s_signal}"

    # 操作建议
    if score > 15:
        suggestion = "🟢 市场情绪好转，可适当加仓"
    elif score < -15:
        suggestion = "🔴 市场情绪恶化，注意控制仓位"
    elif score > 5:
        suggestion = "🟡 情绪偏暖，维持现有仓位"
    elif score < -5:
        suggestion = "🟡 情绪偏弱，观望为主"
    else:
        suggestion = "⚪ 情绪中性，按既定策略操作"

    return {
        "brief": brief,
        "suggestion": suggestion,
        "score": score,
        "direction_emoji": dir_str.split()[0] if " " in dir_str else "➡️",
        "confidence_label": conf_str,
        "predicted_range": s_range,
    }


def full_report():
    """完整预测报告"""
    print("\n" + "=" * 50)
    print("  🔮 市场预测")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    # 情绪预测
    hist = load_sentiment_history(30)
    sentiment_pred = predict_sentiment(hist)
    print(f"\n  📊 情绪预测:")
    print(f"    当前: {sentiment_pred['latest']}")
    print(f"    方向: {sentiment_pred['direction']}")
    print(f"    信号: {sentiment_pred['signal']}")
    print(f"    置信度: {sentiment_pred['confidence']}")
    print(f"    未来3天区间: {sentiment_pred['range_3d']}")
    print(f"    短期均线(3日): {sentiment_pred['ma_3']}")
    print(f"    中期均线(7日): {sentiment_pred['ma_7']}")

    # 市场预测
    fund_data = load_fund_nav(14)
    market_pred = predict_market(fund_data)
    print(f"\n  📈 市场走势:")
    print(f"    方向: {market_pred['direction']}")
    print(f"    近3日平均收益: {market_pred.get('avg_return_3d', 0)*100:.2f}%")

    # 新闻热度
    news_vol = load_news_volume(7)
    news_pred = predict_news_heat(news_vol)
    print(f"\n  📰 新闻热度:")
    print(f"    趋势: {news_pred['trend']}")
    print(f"    日均(近3日): {news_pred.get('avg_daily_3d', 0)} 条")

    # 综合
    summary = generate_summary(sentiment_pred, market_pred, news_pred)
    print(f"\n  {'=' * 50}")
    print(f"  {summary['brief']}")
    print(f"  💡 {summary['suggestion']}")
    print(f"  {'=' * 50}\n")

    return summary


def brief_prediction():
    """一句话预测（供 briefing_push.py 调用）"""
    hist = load_sentiment_history(30)
    sentiment_pred = predict_sentiment(hist)

    if sentiment_pred.get("direction") == "unknown":
        return "数据积累中，暂无法预测"

    score = sentiment_pred.get("score", 0)
    conf = sentiment_pred.get("confidence", 0)
    s_range = sentiment_pred.get("range_3d", "?")
    s_signal = sentiment_pred.get("signal", "")

    if score > 15:
        suggestion = "🟢 可适当加仓"
    elif score < -15:
        suggestion = "🔴 注意控制仓位"
    elif score > 5:
        suggestion = "🟡 维持仓位"
    elif score < -5:
        suggestion = "🟡 观望为主"
    else:
        suggestion = "⚪ 按策略操作"

    return "方向=%s 置信度=%.0f%% 区间=%s 建议=%s" % (
        sentiment_pred.get("direction", "?"),
        conf * 100,
        s_range,
        suggestion,
    )


def main():
    import argparse
    parser = argparse.ArgumentParser(description="统计预测模块")
    parser.add_argument("--sentiment", action="store_true", help="只看情绪预测")
    parser.add_argument("--brief", action="store_true", help="一句话预测")
    args = parser.parse_args()

    if args.brief:
        print(brief_prediction())
        return

    if args.sentiment:
        hist = load_sentiment_history(30)
        pred = predict_sentiment(hist)
        for k, v in pred.items():
            print(f"  {k}: {v}")
        return

    full_report()


if __name__ == "__main__":
    main()
