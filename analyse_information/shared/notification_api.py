#!/usr/bin/env python3
"""
通知中心 API 服务器
提供 REST API 接口，允许其他项目发送信号
"""
import os
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading

# 导入通知中心
from notification_center import (
    add_signal,
    process_queue,
    update_preferences,
    get_stats
)

logger = logging.getLogger(__name__)

class NotificationAPIHandler(BaseHTTPRequestHandler):
    """API 请求处理器"""
    
    def do_GET(self):
        """处理 GET 请求"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        query_params = parse_qs(parsed_path.query)
        
        if path == '/health':
            self._send_response(200, {'status': 'ok'})
        elif path == '/stats':
            stats = get_stats()
            self._send_response(200, stats)
        else:
            self._send_response(404, {'error': 'Not found'})
    
    def do_POST(self):
        """处理 POST 请求"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # 读取请求体
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
        except json.JSONDecodeError:
            self._send_response(400, {'error': 'Invalid JSON'})
            return
        
        if path == '/signal':
            self._handle_add_signal(data)
        elif path == '/preference':
            self._handle_update_preference(data)
        elif path == '/process':
            self._handle_process_queue()
        else:
            self._send_response(404, {'error': 'Not found'})
    
    def _handle_add_signal(self, data):
        """处理添加信号请求"""
        signal = data.get('signal')
        source = data.get('source', 'unknown')
        
        if not signal:
            self._send_response(400, {'error': 'Missing signal data'})
            return
        
        success = add_signal(signal, source)
        
        if success:
            self._send_response(200, {'status': 'added', 'message': 'Signal added to queue'})
        else:
            self._send_response(200, {'status': 'duplicate', 'message': 'Signal already exists'})
    
    def _handle_update_preference(self, data):
        """处理更新偏好请求"""
        signal = data.get('signal')
        action = data.get('action')
        
        if not signal or not action:
            self._send_response(400, {'error': 'Missing signal or action'})
            return
        
        update_preferences(signal, action)
        self._send_response(200, {'status': 'updated', 'message': 'Preference updated'})
    
    def _handle_process_queue(self):
        """处理队列处理请求"""
        process_queue()
        self._send_response(200, {'status': 'processed', 'message': 'Queue processed'})
    
    def _send_response(self, status_code, data):
        """发送响应"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def log_message(self, format, *args):
        """记录日志"""
        logger.info(f"{self.address_string()} - {format % args}")

class NotificationAPIServer:
    """API 服务器"""
    
    def __init__(self, host='0.0.0.0', port=8080):
        self.host = host
        self.port = port
        self.server = None
        self.server_thread = None
    
    def start(self):
        """启动服务器"""
        self.server = HTTPServer((self.host, self.port), NotificationAPIHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()
        
        logger.info(f"Notification API server started on {self.host}:{self.port}")
        print(f"Notification API server started on {self.host}:{self.port}")
    
    def stop(self):
        """停止服务器"""
        if self.server:
            self.server.shutdown()
            self.server_thread.join()
            logger.info("Notification API server stopped")

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Notification Center API Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind')
    parser.add_argument('--port', type=int, default=8080, help='Port to bind')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Log level')
    
    args = parser.parse_args()
    
    # 配置日志
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 创建并启动服务器
    server = NotificationAPIServer(args.host, args.port)
    server.start()
    
    try:
        # 保持主线程运行
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.stop()

if __name__ == '__main__':
    main()
