#!/bin/bash
# MiroFish 单视频完整流水线 - 主入口
# 接受：YouTube URL 或本地视频路径
# 流程：01_download → 02_transcribe → 03_generate_report → 04_update_checklist

set -e

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
VENV="$MONO_ROOT/mem0-venv"
STEP_ENV="/tmp/mirofish_step.env"

# 加载 monorepo .env（API keys: BAILIAN_API_KEY, TAVILY_API_KEY, etc.）
ENV_FILE="$MONO_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo ""
    echo -e "${BLUE}=================================================="
    echo "  $1"
    echo -e "==================================================${NC}"
    echo ""
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# 检查参数
if [ $# -lt 1 ]; then
    print_error "缺少参数"
    echo "用法：$0 <youtube_url_or_local_path>"
    echo ""
    echo "例子："
    echo "  $0 'https://www.youtube.com/watch?v=dXXXXXXXXXX'"
    echo "  $0 '/path/to/video.mp4'"
    exit 1
fi

INPUT="$1"

# Detect --v4 flag early (for step 0)
USE_V4="false"
for arg in "$@"; do
    if [ "$arg" = "--v4" ]; then
        USE_V4="true"
        break
    fi
done

print_header "MiroFish 单视频完整流水线"

# 激活虚拟环境
if [ ! -d "$VENV" ]; then
    print_error "虚拟环境不存在：$VENV"
    exit 1
fi

print_success "激活虚拟环境：$VENV"
source "$VENV/bin/activate"

# === 第 0 步：统一内容获取（monofetchers）===
print_header "第 0 步：统一内容获取（monofetchers）"

FALLBACK="false"
if python3 "$SCRIPT_DIR/00_fetch.py" "$INPUT" ${USE_V4:+--v4} 2>&1; then
    # Check if monofetchers handled it or requested fallback
    if grep -q "FALLBACK=true" "$STEP_ENV" 2>/dev/null; then
        echo ""
        print_warning "monofetchers could not handle this input — using legacy pipeline"
        FALLBACK="true"
    else
        print_success "monofetchers 获取完成（跳过下载 + 转录步骤）"
    fi
else
    echo ""
    print_warning "00_fetch.py 执行失败 — 使用传统流水线"
    FALLBACK="true"
fi

# === 第 1 步：下载视频 / 检查本地文件（传统，仅 fallback）===
if [ "$FALLBACK" = "true" ]; then
    print_header "第 1 步：下载视频 / 检查本地文件（传统）"

    if bash "$SCRIPT_DIR/01_download.sh" "$INPUT"; then
        print_success "下载步骤完成"
    else
        print_error "下载步骤失败"
        exit 1
    fi

    # === 第 2 步：生成字幕（传统，仅 fallback）===
    print_header "第 2 步：生成字幕（传统）"

    if python3 "$SCRIPT_DIR/02_transcribe.py"; then
        print_success "字幕生成步骤完成"
    else
        print_error "字幕生成步骤失败"
        exit 1
    fi
fi

# === 第 2.5 步：更新清单（确保新视频进入 checklist，供报告生成器使用）===
print_header "第 2.5 步：更新清单（pre-report）"

if python3 "$SCRIPT_DIR/04_update_checklist.py"; then
    print_success "清单预更新完成"
else
    print_warning "清单预更新失败，报告生成可能受影响"
fi

# === 第 3 步：生成报告 ===
print_header "第 3 步：生成 MiroFish 报告"

if python3 "$SCRIPT_DIR/03_generate_report.py" "$@"; then
    print_success "报告生成步骤完成"
else
    print_warning "报告生成失败（可能是 API 问题），继续更新清单"
    # 不中止，继续更新清单
fi

# === 第 4 步：更新清单（post-report，同步报告状态）===
print_header "第 4 步：更新清单（post-report）"

if python3 "$SCRIPT_DIR/04_update_checklist.py"; then
    print_success "清单更新步骤完成"
else
    print_error "清单更新步骤失败"
    exit 1
fi

# === 完成 ===
print_header "流水线完成 🎉"

if [ -f "$STEP_ENV" ]; then
    echo "中间环境变量（/tmp/mirofish_step.env）："
    cat "$STEP_ENV"
fi

print_success "所有步骤已完成！"
