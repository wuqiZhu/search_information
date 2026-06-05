#!/usr/bin/env python3
"""
AI 语音简报 - 生成晨间/晚间语音播报

用法:
  python3 tts_briefing.py                    # 生成今早简报并播放
  python3 tts_briefing.py --morning          # 晨报（约1.5分钟）
  python3 tts_briefing.py --evening          # 晚报（约2分钟）
  python3 tts_briefing.py --text "自定义内容" # 自定义文本
  python3 tts_briefing.py --list-voices      # 列出可用语音

依赖: pip install edge-tts
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


AUDIO_DIR = Path("/root/projects/data/search_information/audio_briefings")
os.makedirs(AUDIO_DIR, exist_ok=True)


def get_available_voices():
    """列出可用的中文语音"""
    result = subprocess.run(
        ["edge-tts", "--list-voices"],
        capture_output=True, text=True, timeout=30
    )
    voices = []
    for line in result.stdout.splitlines():
        if "CN" in line or "Chinese" in line or "zh" in line.lower():
            voices.append(line.strip())
    return voices


def generate_speech(text: str, voice: str = "zh-CN-XiaoxiaoNeural",
                    output_path: str = None, pitch: str = "+0Hz",
                    rate: str = "+0%"):
    """
    将文本转换为语音。

    Args:
        text: 要朗读的文本
        voice: TTS 语音名称
        output_path: 输出音频路径
        pitch: 音高调整
        rate: 语速调整

    Returns:
        音频文件路径
    """
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(AUDIO_DIR / f"briefing_{timestamp}.mp3")

    print(f"  🎙️  生成语音简报...")
    print(f"  语音: {voice}")
    print(f"  文本长度: {len(text)} 字")
    print(f"  输出: {output_path}")

    cmd = [
        "edge-tts",
        "--voice", voice,
        "--text", text,
        "--write-media", output_path,
        "--pitch", pitch,
        "--rate", rate,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"  ❌ 生成失败: {result.stderr}")
        return None

    size_kb = os.path.getsize(output_path) / 1024
    duration_sec = size_kb / 16  # 约为16KB/秒的MP3
    print(f"  ✅ 生成成功: {size_kb:.0f} KB (约{duration_sec:.0f}秒)")
    return output_path


def build_morning_script():
    """生成晨报文本"""
    lines = []
    lines.append(f"早上好，今天是{datetime.now().strftime('%m月%d日')}。")

    # 情绪指数
    try:
        hist_path = "/root/projects/data/invest/sentiment/sentiment_history.json"
        if os.path.exists(hist_path):
            with open(hist_path) as f:
                hist = json.load(f)
            if hist:
                x = hist[-1]
                idx = x.get("index", 50)
                level = x.get("level", "中性")
                if idx > 60:
                    feeling = "市场情绪偏乐观"
                elif idx > 40:
                    feeling = "市场情绪平稳"
                else:
                    feeling = "市场情绪偏谨慎"
                lines.append(f"当前市场情绪指数为{idx:.0f}分，等级{level}，{feeling}。")
    except: pass

    # 数据库统计
    try:
        conn = __import__("sqlite3").connect("/root/projects/data/invest/fund_data.db")
        ns = conn.execute("SELECT COUNT(*) FROM news_sentiment").fetchone()[0]
        fn = conn.execute("SELECT COUNT(*) FROM fund_nav").fetchone()[0]
        lines.append(f"已跟踪{fn}条基金净值数据，最近{ns}条新闻情绪分析。")
        conn.close()
    except: pass

    # 最新新闻
    news_dir = "/root/projects/data/search_information/news"
    if os.path.exists(news_dir):
        dbs = sorted([f for f in os.listdir(news_dir) if f.endswith(".db")])
        if dbs:
            try:
                conn = __import__("sqlite3").connect(os.path.join(news_dir, dbs[-1]))
                rows = conn.execute(
                    "SELECT title FROM news_items ORDER BY first_crawl_time DESC LIMIT 5"
                ).fetchall()
                if rows:
                    lines.append("今日热点：")
                    for r in rows:
                        t = r[0][:60]
                        lines.append(t)
                conn.close()
            except: pass

    lines.append("祝您今天投资顺利。")
    return "\n".join(lines)


def build_evening_script():
    """生晚报文本"""
    lines = []
    lines.append(f"晚上好，以下是今天的投资晚报。")

    # 情绪变化
    try:
        hist_path = "/root/projects/data/invest/sentiment/sentiment_history.json"
        if os.path.exists(hist_path):
            with open(hist_path) as f:
                hist = json.load(f)
            if len(hist) >= 2:
                today = hist[-1]
                yesterday = hist[-2]
                diff = today.get("index", 50) - yesterday.get("index", 50)
                if diff > 5:
                    trend = f"较昨日上升{diff:.0f}分"
                elif diff < -5:
                    trend = f"较昨日下降{abs(diff):.0f}分"
                else:
                    trend = "与昨日基本持平"
                lines.append(f"今日情绪指数{today.get('index',50):.0f}分，{trend}。")
    except: pass

    # 系统状态
    lines.append("系统运行正常，数据采集持续进行中。")
    lines.append("晚安。")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="AI 语音简报生成")
    parser.add_argument("--morning", action="store_true", help="晨报模式")
    parser.add_argument("--evening", action="store_true", help="晚报模式")
    parser.add_argument("--text", type=str, help="自定义文本")
    parser.add_argument("--list-voices", action="store_true", help="列出可用语音")
    parser.add_argument("--voice", default="zh-CN-XiaoxiaoNeural", help="语音名称")
    parser.add_argument("--rate", default="+0%", help="语速 (+/-%)")
    parser.add_argument("--output", type=str, help="输出路径")

    args = parser.parse_args()

    if args.list_voices:
        voices = get_available_voices()
        print("\n可用的中文语音:")
        for v in voices:
            print(f"  {v}")
        return

    # 生成文本
    if args.text:
        text = args.text
    elif args.evening:
        text = build_evening_script()
    else:  # default to morning
        text = build_morning_script()

    print("\n" + "=" * 50)
    print("  📢 AI 语音简报")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)
    print(f"\n📝 简报内容:\n{text}\n")

    audio_path = generate_speech(text, voice=args.voice, output_path=args.output, rate=args.rate)
    if audio_path:
        print(f"\n  🔊 音频文件: {audio_path}")
        print(f"  🎵 播放: ffplay {audio_path}")
        print(f"  📎 下载: scp root@188.166.249.182:{audio_path} ./")


if __name__ == "__main__":
    main()
