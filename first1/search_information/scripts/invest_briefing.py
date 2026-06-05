# -*- coding: utf-8 -*-
"""
投资简报生成器 — 接入钉钉推送

每天生成投资建议+教育说明，让非金融专业用户也能理解。

用法:
    python3 invest_briefing.py              # 生成简报
    python3 invest_briefing.py --push       # 生成并推送到钉钉
    python3 invest_briefing.py --learn 止损  # 查某个金融概念的解释
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

# ── 配置 ──
INVEST_API = "http://localhost:5000"
DINGTALK_WEBHOOK = os.environ.get("DINGTALK_WEBHOOK_URL") or ""
DATA_DIR = Path("/root/projects/data/invest")

# ── 金融知识库（大白话解释） ──
KNOWLEDGE_BASE = {
    "止损": (
        "**止损** 就像你买了个东西发现买贵了，设个底线价，跌到这个价就卖掉。\n"
        "目的：防止亏更多。比如你100块买的，设90块止损，最多亏10块。\n"
        "不设止损的后果：就像你现在持仓里那只亏了50%的基金。"
    ),
    "仓位": (
        "**仓位** 就是你总共打算投多少钱，现在已经投了多少。\n"
        "例：你打算投1万，已经投了3000，就是30%仓位。\n"
        "仓位越低，风险越小，但也赚得少。关键是要在自己睡得着觉的水平。"
    ),
    "情绪指数": (
        "**情绪指数** 是看市场上的人现在是贪婪还是恐惧。\n"
        "0-100分：分越低越恐惧，越高越贪婪。\n"
        "参考：恐惧时(<=40)可以买入（别人害怕你贪婪），"
        "贪婪时(>=70)要小心（别人疯狂你冷静）。\n"
        "当前市场情绪：恐惧(39) — 理论上是不错的买入时机。"
    ),
    "净值": (
        "**净值(NAV)** 就是一份基金现在值多少钱。\n"
        "就像你买了一块地，地价涨了你的地就值更多。\n"
        "你买的时候净值是8.9，现在是4.37，跌了50%。\n"
        "净值会每天变化，反映基金持仓的涨跌。"
    ),
    "均摊成本": (
        "**均摊成本** 是你多次买入后平均每份花的钱。\n"
        "例：第一次100块买了10份(10元/份)，第二次100块买了20份(5元/份)。\n"
        "均摊成本 = 总花费200 / 总份数30 = 6.67元/份。\n"
        "如果当前净值 > 均摊成本 → 你就赚了。"
    ),
    "定投": (
        "**定投** 是每隔固定时间投固定金额，不管涨跌。\n"
        "好处：跌的时候买得多（摊低成本），涨的时候买得少。\n"
        "长期下来，均摊成本会比市场平均低。适合没时间盯盘的人。"
    ),
    "收益率": (
        "**收益率** = (现在价值 - 投入本金) / 投入本金 × 100%\n"
        "正数=赚了，负数=亏了。\n"
        "你现在的收益率-22.78%意味着：投100块，现在只剩77块。\n"
        "年化收益率>10%算优秀，>20%非常厉害。"
    ),
}


def fetch_api(path: str) -> dict:
    """调用 invest API"""
    url = f"{INVEST_API}{path}"
    try:
        resp = urllib.request.urlopen(url, timeout=10).read()
        return json.loads(resp)
    except Exception as e:
        return {"error": str(e)}


def generate_briefing() -> str:
    """生成投资简报"""
    # 获取数据
    portfolio = fetch_api("/api/portfolio")
    stats = fetch_api("/api/stats")
    sentiment = fetch_api("/api/market-sentiment?action=current")
    decisions = fetch_api("/api/decisions?days=1")

    holdings = portfolio.get("holdings", [])
    total_value = stats.get("total_value", 0)
    total_profit = stats.get("total_profit", 0)
    profit_rate = stats.get("profit_rate", 0)
    sentiment_index = sentiment.get("index", 50)
    sentiment_level = sentiment.get("level", "中性")

    # 构建消息
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"📋 **投资日报** ({now})", ""]

    # ── 持仓概览 ──
    if profit_rate < -10:
        emoji = "🔴"
    elif profit_rate < 0:
        emoji = "🟡"
    else:
        emoji = "🟢"

    lines.append(f"{emoji} **持仓概览**")
    lines.append(f"  总投资：{stats.get('total_invested', 0):.0f} 元")
    lines.append(f"  当前价值：{total_value:.0f} 元")
    lines.append(f"  总盈亏：{total_profit:+.0f} 元 ({profit_rate:+.1f}%)")
    lines.append("")

    # ── 各基金明细 ──
    lines.append("📊 **各基金明细**")
    for h in holdings:
        code = h["fund_code"]
        name = h.get("fund_name", code)
        rate = h.get("profit_rate", 0)
        nav = h.get("current_nav", 0)
        cost = h.get("avg_cost", 0)

        if rate < -10:
            flag = "🔴"
        elif rate < 0:
            flag = "🟡"
        else:
            flag = "🟢"

        lines.append(f"  {flag} **{name}** ({code})")
        lines.append(f"    收益率：{rate:+.1f}%")
        lines.append(f"    当前净值：{nav:.4f} | 均摊成本：{cost:.4f}")
        lines.append(f"    持有市值：{h.get('current_value', 0):.0f} 元")

        # 教育说明
        if rate < -30:
            lines.append(f"    💡 **知识点：止盈止损**")
            lines.append(f"      这只基金亏了{abs(rate):.0f}%，说明当初没有设止损。")
            lines.append(f"      建议以后买基金前先设好止损线（如-10%就卖）。")
        lines.append("")

    # ── 市场情绪 ──
    lines.append(f"📈 **市场情绪**：{sentiment_level}({sentiment_index})")

    if sentiment_index <= 40:
        lines.append(f"  💡 市场恐惧时，理论上是不错的买入窗口。")
        lines.append(f"  但不要一次性买入，分批建仓更安全。")
    elif sentiment_index >= 70:
        lines.append(f"  ⚠️ 市场贪婪，注意风险，不要追高。")
    else:
        lines.append(f"  市场情绪中性，适合按计划定投。")

    lines.append(f"  📖 *情绪指数越低越恐惧(可买入)，越高越贪婪(该卖出)*")
    lines.append("")

    # ── 操作建议 ──
    lines.append("🎯 **今日建议**")

    for h in holdings:
        code = h["fund_code"]
        rate = h.get("profit_rate", 0)
        nav = h.get("current_nav", 0)
        cost = h.get("avg_cost", 0)

        if rate < -30:
            # 亏很多：不建议现在割肉，但也不建议加仓
            lines.append(f"  **{code}**：亏{rate:.0f}% ⚠️")
            lines.append(f"    建议：**持有观望**，等反弹到-20%以内再考虑")
            lines.append(f"    原因：现在割肉就真的亏了，但加仓风险也大")
            lines.append(f"    学到：买基金一定要设止损线（-10%或-15%）")
        elif rate < -5:
            lines.append(f"  **{code}**：亏{rate:.0f}% 🟡")
            lines.append(f"    建议：**继续持有**，可小额补仓摊低成本")
            lines.append(f"    原因：亏损不大，市场恐惧时补仓是好习惯")
            lines.append(f"    学到：**定投**就是在下跌时多买，上涨时少买")
        elif rate > 5:
            lines.append(f"  **{code}**：赚{rate:.0f}% 🟢")
            lines.append(f"    建议：**部分止盈**，卖掉一半锁定利润")
            lines.append(f"    原因：涨多了就会跌，先落袋为安")
            lines.append(f"    学到：**止盈**和止损一样重要")
        else:
            lines.append(f"  **{code}**：{rate:+.1f}% ⚪")
            lines.append(f"    建议：**继续持有**")
            lines.append(f"    学到：市场波动正常，长期持有是关键")

    lines.append("")

    # ── 今日知识点 ──
    lines.append("📚 **今日知识点**")
    if profit_rate < -20:
        lines.append(KNOWLEDGE_BASE["止损"])
    elif sentiment_index <= 40:
        lines.append(KNOWLEDGE_BASE["情绪指数"])
    else:
        lines.append(KNOWLEDGE_BASE["定投"])

    lines.append("")
    lines.append("---")
    lines.append("投资有风险，以上建议仅供参考。")

    return "\n".join(lines)


def push_to_dingtalk(message: str) -> bool:
    """推送到钉钉"""
    if not DINGTALK_WEBHOOK:
        print("❌ 未配置 DINGTALK_WEBHOOK_URL")
        return False

    data = json.dumps({
        "msgtype": "markdown",
        "markdown": {
            "title": "📋 投资日报",
            "text": message,
        },
    }).encode()

    req = urllib.request.Request(
        DINGTALK_WEBHOOK,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
        if resp.get("errcode") == 0:
            print("✅ 推送成功")
            return True
        else:
            print(f"⚠️ 推送失败: {resp.get('errmsg', '?')}")
            return False
    except Exception as e:
        print(f"❌ 推送异常: {e}")
        return False


def show_knowledge(topic: str):
    """查询某个金融概念"""
    for key, text in KNOWLEDGE_BASE.items():
        if key in topic:
            print(f"\n📖 {key}")
            print("=" * 40)
            print(text)
            return
    print(f"未找到 '{topic}'，可选: {', '.join(KNOWLEDGE_BASE.keys())}")


def main():
    parser = argparse.ArgumentParser(description="投资简报生成器")
    parser.add_argument("--push", action="store_true", help="推送到钉钉")
    parser.add_argument("--learn", type=str, help="查询金融概念（如：止损 定投 净值）")
    parser.add_argument("--output", type=str, help="保存到文件")
    args = parser.parse_args()

    if args.learn:
        show_knowledge(args.learn)
        return

    briefing = generate_briefing()
    print(briefing)

    if args.push:
        print("\n---\n推送中...")
        push_to_dingtalk(briefing)

    if args.output:
        Path(args.output).write_text(briefing, encoding="utf-8")
        print(f"已保存到 {args.output}")


if __name__ == "__main__":
    main()
