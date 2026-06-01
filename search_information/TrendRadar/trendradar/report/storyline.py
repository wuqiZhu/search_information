# coding=utf-8
"""
故事线聚合模块

将相关新闻按时间和来源聚合，形成事件发展脉络
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import defaultdict


def build_storylines(
    report_data: Dict,
    rss_items: Optional[List[Dict]] = None,
    rss_new_items: Optional[List[Dict]] = None,
    max_stories: int = 5,
    max_items_per_story: int = 8,
) -> List[Dict]:
    """
    构建故事线

    将热榜和 RSS 新闻按关键词聚合，形成事件发展脉络

    Args:
        report_data: 热榜报告数据
        rss_items: RSS 统计条目
        rss_new_items: RSS 新增条目
        max_stories: 最多返回的故事线数量
        max_items_per_story: 每个故事线最多包含的新闻条数

    Returns:
        故事线列表，每个故事线包含：
        - keyword: 关键词/主题
        - display_name: 显示名称
        - items: 按时间排序的新闻列表
        - sources: 涉及的来源平台
        - time_range: 时间范围
        - importance: 重要性评分
    """
    stories = []

    # 从热榜数据构建故事线
    if report_data and report_data.get("stats"):
        for stat in report_data["stats"]:
            keyword = stat.get("word", "")
            display_name = stat.get("display_name") or keyword
            titles = stat.get("titles", [])

            if not titles:
                continue

            # 按时间排序
            sorted_titles = _sort_by_time(titles)

            # 收集来源
            sources = set()
            for t in sorted_titles:
                source = t.get("source_name", "")
                if source:
                    sources.add(source)

            # 计算时间范围
            time_range = _get_time_range(sorted_titles)

            # 计算重要性评分
            importance = _calculate_importance(sorted_titles, len(sources))

            stories.append({
                "keyword": keyword,
                "display_name": display_name,
                "items": sorted_titles[:max_items_per_story],
                "sources": list(sources),
                "time_range": time_range,
                "importance": importance,
                "item_count": len(sorted_titles),
                "source_count": len(sources),
            })

    # 从 RSS 数据构建故事线（如果有关键词分组）
    if rss_items:
        for item_group in rss_items:
            if isinstance(item_group, dict) and item_group.get("word"):
                keyword = item_group.get("word", "")
                display_name = item_group.get("display_name") or keyword
                titles = item_group.get("titles", [])

                if not titles:
                    continue

                sorted_titles = _sort_by_time(titles)
                sources = set()
                for t in sorted_titles:
                    source = t.get("source_name") or t.get("feed_name", "")
                    if source:
                        sources.add(source)

                time_range = _get_time_range(sorted_titles)
                importance = _calculate_importance(sorted_titles, len(sources))

                stories.append({
                    "keyword": keyword,
                    "display_name": display_name,
                    "items": sorted_titles[:max_items_per_story],
                    "sources": list(sources),
                    "time_range": time_range,
                    "importance": importance,
                    "item_count": len(sorted_titles),
                    "source_count": len(sources),
                })

    # 按重要性排序，返回 top N
    stories.sort(key=lambda x: x["importance"], reverse=True)
    return stories[:max_stories]


def _sort_by_time(items: List[Dict]) -> List[Dict]:
    """按时间排序新闻条目"""

    def get_time_key(item):
        # 优先使用 time_display
        time_display = item.get("time_display", "")
        if time_display:
            # 解析 "09:30~10:00" 格式，取最早时间
            if "~" in time_display:
                time_display = time_display.split("~")[0]
            try:
                return datetime.strptime(time_display.strip(), "%H:%M")
            except ValueError:
                pass

        # 其次使用 crawl_time
        crawl_time = item.get("crawl_time", "")
        if crawl_time:
            try:
                return datetime.strptime(crawl_time, "%H:%M")
            except ValueError:
                pass

        # 最后使用 published_at
        published_at = item.get("published_at", "")
        if published_at:
            try:
                if "T" in published_at:
                    return datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                return datetime.strptime(published_at, "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                pass

        # 默认返回当前时间（排在最后）
        return datetime.now()

    return sorted(items, key=get_time_key)


def _get_time_range(items: List[Dict]) -> str:
    """获取时间范围字符串"""
    if not items:
        return ""

    times = []
    for item in items:
        time_display = item.get("time_display", "")
        if time_display:
            if "~" in time_display:
                times.append(time_display.split("~")[0].strip())
            else:
                times.append(time_display.strip())

    if not times:
        return ""

    if len(times) == 1:
        return times[0]

    return f"{times[0]} ~ {times[-1]}"


def _calculate_importance(items: List[Dict], source_count: int) -> float:
    """
    计算故事线重要性评分

    评分因素：
    - 新闻数量：越多越重要
    - 来源数量：跨平台报道越重要
    - 排名：排名越高越重要
    - 时效性：最新新闻的时间
    """
    if not items:
        return 0.0

    # 基础分：新闻数量
    score = min(len(items) * 10, 50)

    # 来源多样性加分
    score += min(source_count * 15, 30)

    # 排名加分
    ranks = []
    for item in items:
        rank = item.get("rank", 0)
        if rank > 0:
            ranks.append(rank)
        # 也检查 ranks 列表
        item_ranks = item.get("ranks", [])
        if item_ranks:
            ranks.extend(item_ranks)

    if ranks:
        min_rank = min(ranks)
        if min_rank <= 3:
            score += 20
        elif min_rank <= 10:
            score += 10

    return score


def render_storyline_html(stories: List[Dict]) -> str:
    """
    渲染故事线 HTML

    Args:
        stories: 故事线列表

    Returns:
        HTML 字符串
    """
    if not stories:
        return ""

    from trendradar.report.helpers import html_escape

    html = """
    <div class="storyline-section">
        <div class="storyline-header">
            <div class="storyline-title">事件脉络</div>
            <div class="storyline-subtitle">相关新闻聚合 · 时间线展示</div>
        </div>
    """

    for i, story in enumerate(stories, 1):
        keyword = story.get("display_name", "")
        items = story.get("items", [])
        sources = story.get("sources", [])
        time_range = story.get("time_range", "")
        item_count = story.get("item_count", 0)
        source_count = story.get("source_count", 0)

        if not items:
            continue

        html += f"""
        <div class="story-card">
            <div class="story-card-header">
                <div class="story-card-number">{i}</div>
                <div class="story-card-info">
                    <div class="story-card-keyword">{html_escape(keyword)}</div>
                    <div class="story-card-meta">
                        <span class="story-meta-item">{item_count} 条报道</span>
                        <span class="story-meta-item">{source_count} 个来源</span>
                        {f'<span class="story-meta-item">{html_escape(time_range)}</span>' if time_range else ''}
                    </div>
                </div>
            </div>
            <div class="story-card-sources">
                {"".join(f'<span class="story-source-tag">{html_escape(s)}</span>' for s in sources[:5])}
            </div>
            <div class="story-timeline">
        """

        for j, item in enumerate(items):
            title = item.get("title", "")
            url = item.get("url") or item.get("mobile_url", "")
            source = item.get("source_name") or item.get("feed_name", "")
            time_display = item.get("time_display", "")
            rank = item.get("rank", 0)

            # 时间线节点样式
            is_first = j == 0
            is_last = j == len(items) - 1
            node_class = "timeline-node-first" if is_first else ("timeline-node-last" if is_last else "timeline-node")

            html += f"""
                <div class="{node_class}">
                    <div class="timeline-dot"></div>
                    <div class="timeline-content">
                        <div class="timeline-time">{html_escape(time_display) if time_display else ''}</div>
                        <div class="timeline-title">
            """

            if url:
                html += f'<a href="{html_escape(url)}" target="_blank" class="timeline-link">{html_escape(title)}</a>'
            else:
                html += html_escape(title)

            html += f"""
                        </div>
                        <div class="timeline-source">{html_escape(source)}</div>
                    </div>
                </div>
            """

        html += """
            </div>
        </div>
        """

    html += """
    </div>
    """

    return html
