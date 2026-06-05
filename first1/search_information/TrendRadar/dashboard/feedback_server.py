#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TrendRadar 反馈服务器
接收用户对信号的反馈（忽略/收藏），用于个性化推荐
"""

import os
import sys
import json
import hashlib
from datetime import datetime
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


# 反馈数据文件
FEEDBACK_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'user_feedback.json')


def load_feedback() -> dict:
    """加载反馈数据"""
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {'signals': {}, 'keywords': {}, 'sources': {}}


def save_feedback(feedback: dict):
    """保存反馈数据"""
    os.makedirs(os.path.dirname(FEEDBACK_FILE), exist_ok=True)
    with open(FEEDBACK_FILE, 'w', encoding='utf-8') as f:
        json.dump(feedback, f, ensure_ascii=False, indent=2)


def update_feedback(signal_hash: str, action: str, signal_info: dict):
    """更新反馈数据"""
    feedback = load_feedback()
    
    # 更新信号反馈
    if signal_hash not in feedback['signals']:
        feedback['signals'][signal_hash] = {
            'title': signal_info.get('title', ''),
            'source': signal_info.get('source', ''),
            'keywords': signal_info.get('keywords', []),
            'actions': []
        }
    
    feedback['signals'][signal_hash]['actions'].append({
        'action': action,
        'timestamp': datetime.now().isoformat()
    })
    
    # 更新关键词权重
    for keyword in signal_info.get('keywords', []):
        if keyword not in feedback['keywords']:
            feedback['keywords'][keyword] = {'ignore': 0, 'favorite': 0, 'click': 0}
        feedback['keywords'][keyword][action] = feedback['keywords'][keyword].get(action, 0) + 1
    
    # 更新来源权重
    source = signal_info.get('source', '未知')
    if source not in feedback['sources']:
        feedback['sources'][source] = {'ignore': 0, 'favorite': 0, 'click': 0}
    feedback['sources'][source][action] = feedback['sources'][source].get(action, 0) + 1
    
    save_feedback(feedback)
    return feedback


class FeedbackHandler(BaseHTTPRequestHandler):
    """反馈处理类"""
    
    def do_GET(self):
        """处理 GET 请求"""
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        params = parse_qs(parsed_url.query)
        
        if path == '/feedback':
            # 处理反馈请求
            signal_hash = params.get('hash', [''])[0]
            action = params.get('action', [''])[0]
            title = params.get('title', [''])[0]
            source = params.get('source', [''])[0]
            keywords = params.get('keywords', [''])[0].split(',')
            
            if signal_hash and action in ['ignore', 'favorite', 'click']:
                signal_info = {
                    'title': title,
                    'source': source,
                    'keywords': keywords
                }
                feedback = update_feedback(signal_hash, action, signal_info)
                
                # 返回成功页面
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                
                action_text = {
                    'ignore': '已忽略',
                    'favorite': '已收藏',
                    'click': '已记录点击'
                }.get(action, '未知操作')
                
                html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>TrendRadar 反馈</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
               display: flex; justify-content: center; align-items: center; height: 100vh; 
               background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); margin: 0; }}
        .card {{ background: white; padding: 40px; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); text-align: center; }}
        h1 {{ color: #333; margin-bottom: 20px; }}
        .icon {{ font-size: 48px; margin-bottom: 20px; }}
        .message {{ color: #666; font-size: 18px; }}
        .title {{ color: #667eea; font-weight: bold; margin: 10px 0; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">✅</div>
        <h1>反馈成功</h1>
        <div class="title">{title[:50]}</div>
        <div class="message">{action_text}</div>
        <div class="message" style="margin-top: 20px; font-size: 14px; color: #999;">
            感谢您的反馈，系统将根据您的偏好优化推荐
        </div>
    </div>
</body>
</html>"""
                self.wfile.write(html.encode())
            else:
                # 参数错误
                self.send_response(400)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(b'Invalid parameters')
        
        elif path == '/stats':
            # 返回统计信息
            feedback = load_feedback()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            
            stats = {
                'total_signals': len(feedback['signals']),
                'total_feedback': sum(len(s['actions']) for s in feedback['signals'].values()),
                'top_keywords': sorted(feedback['keywords'].items(), 
                                      key=lambda x: x[1].get('favorite', 0), 
                                      reverse=True)[:10],
                'top_sources': sorted(feedback['sources'].items(), 
                                     key=lambda x: x[1].get('favorite', 0), 
                                     reverse=True)[:5]
            }
            
            self.wfile.write(json.dumps(stats, ensure_ascii=False).encode())
        
        elif path == '/':
            # 首页
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            
            feedback = load_feedback()
            
            html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>TrendRadar 反馈统计</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
               margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                   color: white; padding: 30px; border-radius: 15px; margin-bottom: 20px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }}
        .card {{ background: white; padding: 25px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .card h2 {{ color: #333; margin-top: 0; }}
        .stat {{ font-size: 36px; font-weight: bold; color: #667eea; }}
        .keyword {{ display: inline-block; background: #e8e8e8; padding: 5px 15px; 
                    border-radius: 20px; margin: 5px; font-size: 14px; }}
        .keyword.favorite {{ background: #d4edda; color: #155724; }}
        .keyword.ignore {{ background: #f8d7da; color: #721c24; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 TrendRadar 反馈统计</h1>
            <p>用户偏好分析和信号优化</p>
        </div>
        <div class="grid">
            <div class="card">
                <h2>📈 统计概览</h2>
                <div class="stat">{len(feedback['signals'])}</div>
                <div>总信号数</div>
                <div class="stat" style="margin-top: 20px;">{sum(len(s['actions']) for s in feedback['signals'].values())}</div>
                <div>总反馈次数</div>
            </div>
            <div class="card">
                <h2>🔥 收藏关键词</h2>
                {"".join(f'<span class="keyword favorite">{kw} ({v.get("favorite", 0)})</span>' 
                        for kw, v in sorted(feedback['keywords'].items(), 
                                           key=lambda x: x[1].get('favorite', 0), 
                                           reverse=True)[:10])}
            </div>
            <div class="card">
                <h2>🚫 忽略关键词</h2>
                {"".join(f'<span class="keyword ignore">{kw} ({v.get("ignore", 0)})</span>' 
                        for kw, v in sorted(feedback['keywords'].items(), 
                                           key=lambda x: x[1].get('ignore', 0), 
                                           reverse=True)[:10])}
            </div>
        </div>
    </div>
</body>
</html>"""
            self.wfile.write(html.encode())
        
        else:
            self.send_response(404)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(b'Not Found')
    
    def log_message(self, format, *args):
        """自定义日志格式"""
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {args[0]}")


def main():
    """主函数"""
    port = 8080
    server = HTTPServer(('localhost', port), FeedbackHandler)
    
    print("=" * 50)
    print("TrendRadar 反馈服务器")
    print("=" * 50)
    print(f"服务器地址: http://localhost:{port}")
    print(f"反馈链接: http://localhost:{port}/feedback?hash=XXX&action=ignore/favorite")
    print(f"统计页面: http://localhost:{port}/")
    print("=" * 50)
    print("按 Ctrl+C 停止服务器")
    print("=" * 50)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止")
        server.server_close()


if __name__ == '__main__':
    main()
