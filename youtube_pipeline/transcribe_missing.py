#!/usr/bin/env python3
"""
MiroFish 批量转录工具 - 为所有缺少字幕的视频生成字幕
支持并行处理、自动跳过已有字幕的视频、支持中断恢复
"""

import os
import sys
import json
import argparse
import logging
import signal
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

from config import (
    YOUTUBE_DIR, CHECKLIST_PATH, CHANNELS
)

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path(YOUTUBE_DIR).parent / "mirofish_transcribe.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 全局标志：用于优雅中断
_shutdown_requested = False
_executor = None

def _signal_handler(signum, frame):
    """处理 Ctrl+C / SIGINT 信号"""
    global _shutdown_requested
    _shutdown_requested = True
    print("\n")
    logger.warning("📌 收到中断信号，正在安全关闭...")
    if _executor:
        logger.info("等待当前任务完成...")
    sys.exit(130)

# 注册信号处理器
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def check_keyboard_interrupt():
    """检查用户是否按下 q 键退出（非阻塞式）"""
    import select
    import tty
    import termios

    if not sys.stdin.isatty():
        return False

    # 保存终端设置
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        tty.setraw(fd)
        # 非阻塞检查是否有输入
        if select.select([sys.stdin], [], [], 0.1)[0]:
            ch = sys.stdin.read(1)
            if ch.lower() == 'q':
                return True
    finally:
        # 恢复终端设置
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    return False

# 并行处理配置（Whisper 是 CPU 密集型，建议不超过 2）
MAX_PARALLEL_JOBS = 2


class ChecklistManager:
    """管理 checklist.json 的读写"""

    def __init__(self, checklist_path=CHECKLIST_PATH):
        self.checklist_path = Path(checklist_path)

    def load(self):
        """读取 checklist.json"""
        if self.checklist_path.exists():
            with open(self.checklist_path, encoding='utf-8') as f:
                return json.load(f)
        return {"enabled": False, "videos": {}}

    def save(self, data):
        """保存 checklist.json"""
        data["last_scanned"] = datetime.now().isoformat()
        with open(self.checklist_path, "w", encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def update_video_status(self, video_id, has_transcript=True, transcript_path=None):
        """更新单个视频的转录状态"""
        checklist = self.load()
        if video_id in checklist.get("videos", {}):
            checklist["videos"][video_id]["has_transcript"] = has_transcript
            if has_transcript and transcript_path:
                checklist["videos"][video_id]["transcript_path"] = transcript_path
            if has_transcript and checklist["videos"][video_id].get("report_status") == "no_transcript":
                checklist["videos"][video_id]["report_status"] = "pending"
            checklist["videos"][video_id]["processed_at"] = datetime.now().isoformat()
            self.save(checklist)
        return checklist["videos"].get(video_id)


def extract_vtt_to_txt(vtt_path, txt_path):
    """从 VTT 提取文本内容到 TXT"""
    import re

    try:
        with open(vtt_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        logger.error(f"  ❌ 读取 VTT 失败：{e}")
        return False

    output_lines = []
    for line in lines:
        line = line.rstrip('\n')

        # 跳过 VTT 头部
        if line.startswith('WEBVTT'):
            continue

        # 跳过空行和时间戳行
        if not line or '-->' in line:
            continue

        # 跳过纯数字行（cue 编号）
        if line.isdigit():
            continue

        # 移除内联时间戳
        line = re.sub(r'<\d{2}:\d{2}:\d{2}>', '', line).strip()

        if line:
            output_lines.append(line)

    try:
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(output_lines))
        logger.info(f"  ✅ 已保存：{txt_path.name}")
        return True
    except Exception as e:
        logger.error(f"  ❌ 写入 TXT 失败：{e}")
        return False


def transcribe_with_whisper(video_path, output_dir, model_size="base"):
    """使用 Whisper 转录视频"""
    if not WHISPER_AVAILABLE:
        logger.error("  ❌ faster-whisper 未安装，请运行：pip install faster-whisper")
        return None

    video_path = Path(video_path)
    stem = video_path.stem
    vtt_path = Path(output_dir) / f"{stem}.vtt"
    txt_path = Path(output_dir) / f"{stem}.txt"

    # 跳过已存在的字幕
    if vtt_path.exists() and txt_path.exists():
        logger.info(f"  ✓ 字幕已存在（跳过 Whisper）")
        return str(txt_path)

    logger.info(f"  🎙️  加载 Whisper 模型：{model_size}...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    # 提取音频
    wav_path = Path(f"/tmp/{stem}.wav")
    logger.info(f"  🔊 提取音频...")

    try:
        import subprocess
        subprocess.run([
            "/opt/homebrew/bin/ffmpeg", '-i', str(video_path),
            '-vn', '-acodec', 'pcm_s16le',
            '-ar', '16000', '-ac', '1', '-y', str(wav_path)
        ], capture_output=True, timeout=300, check=True)
    except Exception as e:
        logger.error(f"  ❌ 提取音频失败：{e}")
        return None

    file_size_mb = wav_path.stat().st_size / 1024 / 1024
    logger.info(f"  📊 音频：{file_size_mb:.0f}MB，开始转录...")

    try:
        segments, info = model.transcribe(
            str(wav_path),
            beam_size=1,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            word_timestamps=False
        )

        vtt_lines = ["WEBVTT\n"]
        txt_lines = []
        seg_idx = 1

        for segment in segments:
            start = segment.start
            end = segment.end
            text = segment.text.strip()
            if not text:
                continue

            # 格式化 VTT 时间戳
            def fmt_ts(s):
                h = int(s // 3600)
                m = int((s % 3600) // 60)
                sec = int(s % 60)
                ms = int((s % 1) * 1000)
                return f"{h:02d}:{m:02d}:{sec:02d}.{ms:03d}"

            vtt_lines.append(f"{seg_idx}")
            vtt_lines.append(f"{fmt_ts(start)} --> {fmt_ts(end)}")
            vtt_lines.append(text)
            vtt_lines.append("")
            txt_lines.append(text)
            seg_idx += 1

        if len(txt_lines) < 5:
            logger.warning(f"  ⚠️  仅转录 {len(txt_lines)} 个分段，可能未成功")
            return None

        # 保存 VTT
        vtt_path.parent.mkdir(parents=True, exist_ok=True)
        vtt_path.write_text("\n".join(vtt_lines), encoding="utf-8")

        # 保存 TXT
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        txt_path.write_text(" ".join(txt_lines), encoding="utf-8")

        logger.info(f"  ✅ 转录完成：{len(txt_lines)} 个分段，{len(' '.join(txt_lines))} 字")

        # 清理临时文件
        wav_path.unlink(missing_ok=True)
        return str(txt_path)

    except Exception as e:
        logger.error(f"  ❌ 转录失败：{e}")
        wav_path.unlink(missing_ok=True)
        return None


def find_video_file(video_id, full_name, channel):
    """查找视频文件路径"""
    # 可能的文件名模式
    possible_names = [
        f"{full_name}.mp4",
        f"{full_name}.mkv",
        f"{full_name}.webm",
    ]

    # 搜索目录
    search_dirs = []
    if channel and channel != "Unknown":
        search_dirs.append(Path(YOUTUBE_DIR) / channel)
    search_dirs.append(Path(YOUTUBE_DIR))

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for possible_name in possible_names:
            video_file = search_dir / possible_name
            if video_file.exists():
                return video_file

    return None


def transcript_exists(video_id, full_name, channel=None):
    """检查字幕文件是否存在"""
    # 可能的字幕文件名模式
    if full_name.endswith(f'[{video_id}]'):
        possible_txt = f"{full_name}.txt"
        possible_vtt = f"{full_name}.vtt"
        possible_srt = f"{full_name}.srt"
    else:
        possible_txt = f"{full_name} [{video_id}].txt"
        possible_vtt = f"{full_name} [{video_id}].vtt"
        possible_srt = f"{full_name} [{video_id}].srt"

    # 搜索目录
    search_dirs = []
    if channel and channel != "Unknown":
        search_dirs.append(Path(YOUTUBE_DIR) / channel)
    search_dirs.append(Path(YOUTUBE_DIR) / "transcripts")
    search_dirs.append(Path(YOUTUBE_DIR))

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for ext in ['.txt', '.vtt', '.srt']:
            subtitle_file = search_dir / (Path(possible_txt).stem + ext)
            if subtitle_file.exists():
                return True

    return False


def transcribe_video(video_id, channel, full_name):
    """转录单个视频"""
    import json

    logger.info(f"\n{'='*70}")
    logger.info(f"📝 处理视频 [{video_id}]: {full_name[:60]}...")
    logger.info(f"{'='*70}")

    # 检查字幕是否已存在
    if transcript_exists(video_id, full_name, channel):
        logger.info(f"  ✓ 字幕已存在，跳过")
        # 更新 checklist 状态
        manager = ChecklistManager()
        checklist = manager.load()
        if video_id in checklist.get("videos", {}):
            checklist["videos"][video_id]["has_transcript"] = True
            # 如果之前是 no_transcript，改为 pending
            if checklist["videos"][video_id].get("report_status") == "no_transcript":
                checklist["videos"][video_id]["report_status"] = "pending"
            manager.save(checklist)
        return True

    # 查找视频文件
    video_path = find_video_file(video_id, full_name, channel)
    if not video_path:
        logger.error(f"  ❌ 视频文件不存在：{full_name}")
        return False

    logger.info(f"  📁 视频路径：{video_path}")

    # 检查是否有 VTT（yt-dlp 自动生成）
    vtt_path = video_path.parent / f"{video_path.stem}.vtt"
    txt_path = video_path.parent / f"{video_path.stem}.txt"

    if vtt_path.exists() and not txt_path.exists():
        logger.info(f"  📄 发现 VTT 字幕，转换为 TXT...")
        if extract_vtt_to_txt(vtt_path, txt_path):
            logger.info(f"  ✅ VTT 转换成功")
            # 更新 checklist
            manager = ChecklistManager()
            checklist = manager.load()
            if video_id in checklist.get("videos", {}):
                checklist["videos"][video_id]["has_transcript"] = True
                checklist["videos"][video_id]["transcript_path"] = str(txt_path)
                if checklist["videos"][video_id].get("report_status") == "no_transcript":
                    checklist["videos"][video_id]["report_status"] = "pending"
                manager.save(checklist)
            return True

    # 使用 Whisper 转录
    logger.info(f"  🎙️  使用 Whisper 生成字幕...")
    result = transcribe_with_whisper(str(video_path), str(video_path.parent), model_size="base")

    if result:
        logger.info(f"  ✅ 转录成功：{result}")
        # 更新 checklist
        manager = ChecklistManager()
        checklist = manager.load()
        if video_id in checklist.get("videos", {}):
            checklist["videos"][video_id]["has_transcript"] = True
            checklist["videos"][video_id]["transcript_path"] = result
            if checklist["videos"][video_id].get("report_status") == "no_transcript":
                checklist["videos"][video_id]["report_status"] = "pending"
            manager.save(checklist)
        return True
    else:
        logger.error(f"  ❌ 转录失败")
        return False


def process_missing_transcripts(max_parallel=MAX_PARALLEL_JOBS):
    """处理所有缺少字幕的视频"""
    import json

    logger.info(f"\n{'='*70}")
    logger.info("🚀 开始批量转录缺少字幕的视频")
    logger.info(f"{'='*70}")
    logger.info(f"设置并行处理数：{max_parallel}")

    manager = ChecklistManager()
    checklist = manager.load()

    # 收集缺少字幕的视频
    missing_videos = []
    for video_id, info in checklist.get("videos", {}).items():
        has_transcript = info.get("has_transcript", False)
        if not has_transcript:
            missing_videos.append({
                "video_id": video_id,
                "channel": info.get("channel", "Unknown"),
                "full_name": info.get("full_name", "Unknown")
            })

    if not missing_videos:
        logger.info("✅ 所有视频都已有字幕，无需转录")
        return

    logger.info(f"📊 发现 {len(missing_videos)} 个视频缺少字幕")

    success_count = 0
    error_count = 0
    skip_count = 0
    start_time = time.time()

    # 使用线程池并行处理
    with ThreadPoolExecutor(max_workers=max_parallel) as executor:
        # 提交所有任务
        future_to_video = {
            executor.submit(
                transcribe_video,
                video["video_id"],
                video["channel"],
                video["full_name"]
            ): video for video in missing_videos
        }

        # 收集结果
        for future in as_completed(future_to_video):
            video = future_to_video[future]
            video_id = video["video_id"]

            try:
                result = future.result()
                if result:
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                logger.error(f"[{video_id}] 处理失败：{e}", exc_info=True)
                error_count += 1

    elapsed = time.time() - start_time
    logger.info(f"\n{'='*70}")
    logger.info("📊 批量转录完成")
    logger.info(f"{'='*70}")
    logger.info(f"✅ 成功：{success_count}")
    logger.info(f"❌ 失败：{error_count}")
    logger.info(f"⏱️  总耗时：{elapsed:.1f}s ({elapsed/max(1, success_count + error_count):.1f}s/个)")
    logger.info(f"{'='*70}\n")


def test_single_video(video_id):
    """测试单个视频的转录"""
    import json

    logger.info(f"\n{'='*70}")
    logger.info(f"🧪 测试模式：转录单个视频")
    logger.info(f"{'='*70}")

    manager = ChecklistManager()
    checklist = manager.load()
    videos = checklist.get("videos", {})

    if video_id not in videos:
        logger.error(f"视频 ID '{video_id}' 不在 checklist 中")
        return False

    video_info = videos[video_id]
    full_name = video_info.get("full_name", "Unknown")
    channel = video_info.get("channel", "Unknown")

    logger.info(f"📺 视频信息:")
    logger.info(f"   ID: {video_id}")
    logger.info(f"   标题：{full_name}")
    logger.info(f"   频道：{channel}")

    # 转录视频
    result = transcribe_video(video_id, channel, full_name)

    if result:
        logger.info(f"✅ 转录成功")
        return True
    else:
        logger.error(f"❌ 转录失败")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="MiroFish 批量转录工具 - 为缺少字幕的视频生成字幕"
    )
    parser.add_argument(
        "--process-all",
        action="store_true",
        help="处理所有缺少字幕的视频（批量转录）"
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=MAX_PARALLEL_JOBS,
        help=f"并行处理的最大任务数（默认：{MAX_PARALLEL_JOBS}，Whisper 是 CPU 密集型，不建议超过 2）"
    )
    parser.add_argument(
        "--test",
        type=str,
        help="测试模式：为指定视频 ID 转录"
    )
    parser.add_argument(
        "--check-deps",
        action="store_true",
        help="检查依赖库"
    )

    args = parser.parse_args()

    if args.check_deps:
        logger.info("📦 依赖检查:")
        logger.info(f"   {'✅' if WHISPER_AVAILABLE else '❌'} faster-whisper")
        logger.info(f"   {'✅' if Path('/opt/homebrew/bin/ffmpeg').exists() else '❌'} ffmpeg (/opt/homebrew/bin/ffmpeg)")
        if not WHISPER_AVAILABLE:
            logger.info("\n缺少依赖库，请运行:")
            logger.info("   pip install faster-whisper")
        return

    if args.test:
        success = test_single_video(args.test)
        sys.exit(0 if success else 1)
    elif args.process_all:
        process_missing_transcripts(max_parallel=args.parallel)
    else:
        logger.info("Usage: python3 scripts/youtube_mirofish/transcribe_missing.py [OPTIONS]")
        logger.info("\nOptions:")
        logger.info("  --process-all           处理所有缺少字幕的视频（批量转录）")
        logger.info("  --parallel N            设置并行处理数（默认：2）")
        logger.info("  --test <video_id>       测试单个视频的转录")
        logger.info("  --check-deps            检查依赖库")


if __name__ == "__main__":
    main()
