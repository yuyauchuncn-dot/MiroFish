#!/bin/bash
# -----------------------------------------------------------------------------
# Cookie 刷新脚本：从本地 Chrome 提取最新 YouTube cookies
# 使用方法：bash refresh_cookies.sh
# -----------------------------------------------------------------------------

set -e

COOKIES_FILE="'$(dirname "${BASH_SOURCE[0]}")/../../..'/data/raw/media/youtube_downloads/cookies.txt"
BACKUP_FILE="${COOKIES_FILE}.bak"

# 清理函数：提供优雅退出
cleanup() {
    echo ""
    echo "📌 操作已中断"
    exit 130
}

# 注册信号处理器
trap cleanup INT TERM

echo "================================================="
echo "正在从本地 Chrome 提取 YouTube cookies..."
echo "================================================="

# 备份旧 cookies
if [ -f "$COOKIES_FILE" ]; then
    cp "$COOKIES_FILE" "$BACKUP_FILE"
    echo "已备份旧 cookies 至: $BACKUP_FILE"
fi

# 从 Chrome 提取最新 cookies（需要 Chrome 已登录 YouTube）
yt-dlp \
    --cookies-from-browser chrome \
    --cookies "$COOKIES_FILE" \
    --skip-download \
    --quiet \
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ" \
    && echo "✓ cookies 提取成功: $COOKIES_FILE" \
    || {
        echo "✗ Chrome cookies 提取失败"
        echo "  请确认："
        echo "  1. Chrome 浏览器已安装"
        echo "  2. Chrome 中已登录 YouTube 账号"
        echo "  3. Chrome 已关闭（某些系统需要关闭浏览器才能读取 cookies）"
        if [ -f "$BACKUP_FILE" ]; then
            cp "$BACKUP_FILE" "$COOKIES_FILE"
            echo "  已还原旧 cookies"
        fi
        exit 1
    }

echo "================================================="
echo "Cookie 刷新完成"
echo "================================================="
