#!/bin/bash
# 诊断脚本：检查 YouTube 下载问题

set -e

DOWNLOAD_ROOT="'$(dirname "${BASH_SOURCE[0]}")/../../..'/data/raw/media/youtube_downloads"
COOKIES_FILE="$DOWNLOAD_ROOT/cookies.txt"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "================================================="
echo "🔍 YouTube 下载诊断"
echo "================================================="
echo ""

# 检查 cookies 文件
echo "1️⃣  检查 cookies 文件..."
if [ ! -f "$COOKIES_FILE" ]; then
    echo "   ❌ cookies 文件不存在: $COOKIES_FILE"
    echo "   💡 运行: bash scripts/youtube_downloads/refresh_cookies.sh"
else
    echo "   ✅ cookies 文件存在"
    # 检查是否包含 YouTube cookies
    if grep -q "youtube.com" "$COOKIES_FILE" 2>/dev/null; then
        echo "   ✅ 包含 YouTube 域名 cookies"
    else
        echo "   ❌ 不包含 YouTube cookies（可能是登录问题）"
        echo "   💡 解决方案："
        echo "      1. 打开 Chrome 浏览器"
        echo "      2. 访问 https://www.youtube.com"
        echo "      3. 使用 Google 账号登录"
        echo "      4. 关闭 Chrome（某些系统需要关闭才能读取 cookies）"
        echo "      5. 运行: bash scripts/youtube_downloads/refresh_cookies.sh"
    fi
    echo ""
    echo "   cookies 文件内容预览（前 20 行）:"
    head -20 "$COOKIES_FILE" | sed 's/^/   /'
fi

echo ""
echo "2️⃣  检查 yt-dlp 版本和配置..."
yt-dlp --version

echo ""
echo "3️⃣  测试下载某个视频..."
echo "   🧪 测试视频: https://www.youtube.com/watch?v=dQw4w9WgXcQ"
echo ""

# 创建临时目录
TEMP_DIR="/tmp/yt-dlp-test-$$"
mkdir -p "$TEMP_DIR"

# 测试下载
if yt-dlp \
    --cookies "$COOKIES_FILE" \
    --quiet \
    --no-warnings \
    --skip-download \
    -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/bestvideo+bestaudio/best" \
    -o "$TEMP_DIR/test.%(ext)s" \
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ" 2>&1 | tee "$TEMP_DIR/test.log"; then
    echo "   ✅ 测试下载成功"
else
    echo "   ❌ 测试下载失败"
    echo ""
    echo "   错误信息:"
    cat "$TEMP_DIR/test.log" | sed 's/^/      /'
fi

# 清理
rm -rf "$TEMP_DIR"

echo ""
echo "4️⃣  可能的解决方案："
echo ""
echo "   A. 如果是地理限制问题："
echo "      - 某些频道可能有地理限制"
echo "      - 可以尝试使用代理或 VPN"
echo "      - 在下载脚本中添加代理参数:"
echo "        --proxy [protocol://]host[:port]"
echo ""
echo "   B. 如果是账号问题："
echo "      - 确保 Chrome 中已登录 YouTube 账号"
echo "      - 账号可能有年龄限制内容限制"
echo "      - 尝试登出再重新登录"
echo ""
echo "   C. 如果是 yt-dlp 过期："
echo "      - 更新 yt-dlp: pip install --upgrade yt-dlp"
echo ""
echo "   D. 如果是频道特定问题："
echo "      - 某些频道可能需要付款或特殊权限"
echo "      - 尝试在浏览器中手动访问频道确认可用性"
echo ""
echo "================================================="
