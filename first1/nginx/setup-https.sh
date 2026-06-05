#!/bin/bash
# HTTPS 证书设置脚本
# 使用方法: bash setup-https.sh your-domain.com

set -e

DOMAIN=${1:-""}
EMAIL=${2:-""}

if [ -z "$DOMAIN" ]; then
    echo "使用方法: bash setup-https.sh <域名> [邮箱]"
    echo "示例: bash setup-https.sh dashboard.example.com admin@example.com"
    echo ""
    echo "如果没有域名，可以使用自签名证书（开发/测试）:"
    echo "bash setup-https.sh --self-signed"
    exit 1
fi

# 自签名证书模式
if [ "$DOMAIN" = "--self-signed" ]; then
    echo "生成自签名证书..."
    
    mkdir -p /etc/nginx/ssl
    
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/nginx/ssl/self-signed.key \
        -out /etc/nginx/ssl/self-signed.crt \
        -subj "/C=CN/ST=Beijing/L=Beijing/O=Dev/CN=localhost"
    
    echo "自签名证书已生成:"
    echo "  证书: /etc/nginx/ssl/self-signed.crt"
    echo "  密钥: /etc/nginx/ssl/self-signed.key"
    echo ""
    echo "注意: 自签名证书浏览器会显示警告，仅用于开发/测试"
    
    # 更新 nginx 配置使用自签名证书
    sed -i 's|ssl_certificate /etc/letsencrypt/live/.*|ssl_certificate /etc/nginx/ssl/self-signed.crt;|' /etc/nginx/nginx.conf
    sed -i 's|ssl_certificate_key /etc/letsencrypt/live/.*|ssl_certificate_key /etc/nginx/ssl/self-signed.key;|' /etc/nginx/nginx.conf
    
    exit 0
fi

# Let's Encrypt 模式
if [ -z "$EMAIL" ]; then
    echo "错误: 使用 Let's Encrypt 需要提供邮箱"
    echo "使用方法: bash setup-https.sh <域名> <邮箱>"
    exit 1
fi

echo "设置 HTTPS 证书 for $DOMAIN..."

# 安装 certbot (如果没有)
if ! command -v certbot &> /dev/null; then
    echo "安装 certbot..."
    apt-get update
    apt-get install -y certbot python3-certbot-nginx
fi

# 停止 nginx
systemctl stop nginx 2>/dev/null || true

# 获取证书
echo "获取 Let's Encrypt 证书..."
certbot certonly --standalone \
    -d "$DOMAIN" \
    --email "$EMAIL" \
    --agree-tos \
    --non-interactive

# 更新 nginx 配置
echo "更新 Nginx 配置..."
sed -i "s|server_name .*|server_name $DOMAIN;|" /etc/nginx/nginx.conf
sed -i "s|ssl_certificate /etc/letsencrypt/live/.*|ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;|" /etc/nginx/nginx.conf
sed -i "s|ssl_certificate_key /etc/letsencrypt/live/.*|ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;|" /etc/nginx/nginx.conf

# 启动 nginx
systemctl start nginx

# 设置自动续期
echo "设置证书自动续期..."
(crontab -l 2>/dev/null; echo "0 12 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'") | crontab -

echo ""
echo "HTTPS 配置完成!"
echo "访问: https://$DOMAIN"
echo ""
echo "证书续期: 已设置自动续期（每天12点检查）"
echo "手动续期: certbot renew"
