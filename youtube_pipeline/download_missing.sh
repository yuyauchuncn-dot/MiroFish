#!/bin/bash
# -----------------------------------------------------------------------------
# 下载缺失视频脚本：从指定 YouTube 频道下载尚未下载的视频（支持并行下载）
# 使用方法：
#   bash download_missing.sh                           # 下载所有默认频道
#   bash download_missing.sh --channel <URL>          # 下载指定频道
#   bash download_missing.sh --channel-all            # 下载所有频道（包括未启用的）
#   bash download_missing.sh [--refresh-cookies] [--parallel]
# 默认为顺序下载；--parallel 启用并行模式
# -----------------------------------------------------------------------------

# 变量保存 PID 用于清理
BG_PIDS=()

# 清理函数：终止所有后台任务
cleanup() {
    if [ ${#BG_PIDS[@]} -gt 0 ]; then
        echo ""
        echo "📌 收到中断信号，正在安全关闭所有下载任务..."
        for pid in "${BG_PIDS[@]}"; do
            kill $pid 2>/dev/null || true
        done
        wait 2>/dev/null || true
    fi
    exit 130
}

# 注册信号处理器
trap cleanup INT TERM EXIT

set -e

DOWNLOAD_ROOT="'$(dirname "${BASH_SOURCE[0]}")/../../..'/data/raw/media/youtube_downloads"
ARCHIVE_FILE="$DOWNLOAD_ROOT/download_archive.txt"
COOKIES_FILE="$DOWNLOAD_ROOT/cookies.txt"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARALLEL_MODE=false
SINGLE_CHANNEL_MODE=false
TARGET_CHANNEL_URL=""
TARGET_CHANNEL_NAME=""

# 所有可用频道（默认只启用部分）
DEFAULT_CHANNEL_URLS=(
    # "https://www.youtube.com/@YiView"
    # "https://www.youtube.com/@RhinoFinance"
    "https://www.youtube.com/@上海刀哥"
    # "https://www.youtube.com/@oldpowerful"
)
DEFAULT_CHANNEL_NAMES=(
    # "張經義"
    # "视野环球财经"
    "上海刀哥"
    # "老厉害"
)

# 所有频道（包括未启用的）用于 --channel-all
ALL_CHANNEL_URLS=(
    "https://www.youtube.com/@YiView"
    "https://www.youtube.com/@RhinoFinance"
    "https://www.youtube.com/@上海刀哥"
    "https://www.youtube.com/@oldpowerful"
)
ALL_CHANNEL_NAMES=(
    "張經義"
    "视野环球财经"
    "上海刀哥"
    "老厉害"
)

# 解析参数
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "用法：bash download_missing.sh [选项]"
    echo ""
    echo "选项:"
    echo "  --channel <URL>      下载指定频道（例如：--channel https://www.youtube.com/@oldpowerful）"
    echo "  --channel-all        下载所有频道（包括未启用的）"
    echo "  --all                同上"
    echo "  --refresh-cookies    刷新 YouTube cookies"
    echo "  --parallel           启用并行下载（多频道同时下载）"
    echo "  --help, -h           显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  # 下载默认频道（上海刀哥）"
    echo "  bash download_missing.sh"
    echo ""
    echo "  # 下载指定频道"
    echo "  bash download_missing.sh --channel https://www.youtube.com/@oldpowerful"
    echo ""
    echo "  # 下载所有频道"
    echo "  bash download_missing.sh --channel-all --parallel"
    exit 0
fi

i=1
while [ $i -le $# ]; do
    arg="${!i}"
    if [ "$arg" = "--refresh-cookies" ]; then
        echo "正在刷新 cookies..."
        bash "$SCRIPT_DIR/refresh_cookies.sh"
    elif [ "$arg" = "--parallel" ]; then
        PARALLEL_MODE=true
    elif [ "$arg" = "--channel" ]; then
        SINGLE_CHANNEL_MODE=true
        i=$((i+1))
        TARGET_CHANNEL_URL="${!i}"
    elif [[ "$arg" == --channel=* ]]; then
        SINGLE_CHANNEL_MODE=true
        TARGET_CHANNEL_URL="${arg#*=}"
    elif [ "$arg" = "--channel-all" ] || [ "$arg" = "--all" ]; then
        SINGLE_CHANNEL_MODE=false
        CHANNEL_URLS=("${ALL_CHANNEL_URLS[@]}")
        CHANNEL_NAMES=("${ALL_CHANNEL_NAMES[@]}")
    fi
    i=$((i+1))
done

# 如果指定了单个频道，需要获取频道名称
if [ "$SINGLE_CHANNEL_MODE" = true ] && [ -n "$TARGET_CHANNEL_URL" ]; then
    # 从 URL 提取频道名称（@xxx 格式）
    CHANNEL_NAME_FROM_URL=$(echo "$TARGET_CHANNEL_URL" | sed 's|.*/@||')
    if [ -z "$CHANNEL_NAME_FROM_URL" ]; then
        CHANNEL_NAME_FROM_URL="unknown"
    fi

    # 尝试从预定义列表中查找频道名称
    FOUND=false
    for i in "${!ALL_CHANNEL_URLS[@]}"; do
        if [ "${ALL_CHANNEL_URLS[$i]}" = "$TARGET_CHANNEL_URL" ]; then
            TARGET_CHANNEL_NAME="${ALL_CHANNEL_NAMES[$i]}"
            FOUND=true
            break
        fi
    done

    # 如果未找到，使用 URL 中的名称
    if [ "$FOUND" = false ]; then
        TARGET_CHANNEL_NAME="$CHANNEL_NAME_FROM_URL"
    fi

    CHANNEL_URLS=("$TARGET_CHANNEL_URL")
    CHANNEL_NAMES=("$TARGET_CHANNEL_NAME")
fi

# 设置 cookies 参数
[ -f "$COOKIES_FILE" ] && COOKIES_OPT="--cookies $COOKIES_FILE" || COOKIES_OPT=""
[ -f "$COOKIES_FILE" ] && echo "使用 cookies: $COOKIES_FILE" || echo "未找到 cookies 文件，尝试无 cookies 下载"

# 初始化频道列表（如果未通过参数设置）
if [ ${#CHANNEL_URLS[@]} -eq 0 ]; then
    CHANNEL_URLS=("${DEFAULT_CHANNEL_URLS[@]}")
    CHANNEL_NAMES=("${DEFAULT_CHANNEL_NAMES[@]}")
fi

touch "$ARCHIVE_FILE"

# 定义下载函数（用于并行模式）
download_channel() {
    local CHANNEL_URL="$1"
    local CHANNEL_NAME="$2"
    local OUTPUT_DIR="$DOWNLOAD_ROOT/$CHANNEL_NAME"

    mkdir -p "$OUTPUT_DIR"

    echo "================================================="
    echo "频道：$CHANNEL_NAME"
    echo "URL：$CHANNEL_URL"
    echo "输出：$OUTPUT_DIR"
    echo "================================================="

    yt-dlp \
        $COOKIES_OPT \
        --ignore-errors \
        --download-archive "$ARCHIVE_FILE" \
        --write-auto-sub \
        --sub-lang "zh-CN,zh-Hans,zh,en" \
        --sub-format "vtt" \
        --format "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/bestvideo+bestaudio/best" \
        --merge-output-format mp4 \
        -o "$OUTPUT_DIR/%(upload_date)s - %(title)s [%(id)s].%(ext)s" \
        "$CHANNEL_URL" \
        && echo "✓ $CHANNEL_NAME 下载完成" \
        || echo "✗ $CHANNEL_NAME 下载出错（已跳过，继续下一个频道）"

    echo ""
}

if [ "$PARALLEL_MODE" = true ]; then
    echo "================================================="
    echo "🚀 启用并行下载模式（最多 ${#CHANNEL_URLS[@]} 个并发任务）"
    echo "================================================="
    echo ""

    # 启动后台任务
    for i in "${!CHANNEL_URLS[@]}"; do
        CHANNEL_URL="${CHANNEL_URLS[$i]}"
        CHANNEL_NAME="${CHANNEL_NAMES[$i]}"
        download_channel "$CHANNEL_URL" "$CHANNEL_NAME" &
        BG_PIDS+=($!)
    done

    # 等待所有后台任务完成
    wait
else
    echo "================================================="
    echo "📊 顺序下载模式"
    echo "================================================="
    echo ""

    for i in "${!CHANNEL_URLS[@]}"; do
        CHANNEL_URL="${CHANNEL_URLS[$i]}"
        CHANNEL_NAME="${CHANNEL_NAMES[$i]}"
        download_channel "$CHANNEL_URL" "$CHANNEL_NAME"
    done
fi

echo "================================================="
echo "所有频道处理完成"
echo "================================================="
