#!/usr/bin/env python3
"""
MiroFish 流水线：第 2 步 - 生成字幕
接受：<video_path> 或从 /tmp/mirofish_step.env 读取
输出：更新 /tmp/mirofish_step.env 中的 TRANSCRIPT_PATH
"""

import os
import sys
import subprocess
import re
from pathlib import Path

STEP_ENV = "/tmp/mirofish_step.env"
YOUTUBE_DIR = Path("Path(__file__).resolve().parent.parent.parent.parent / 'data' / 'raw' / 'media' / 'youtube_downloads'")
TRANSCRIPTS_DIR = YOUTUBE_DIR / "transcripts"

# ASR 错字修正（从 evidence 模块导入）
def _apply_asr_corrections(text: str) -> str:
    """应用 ASR 错别字修正到文本"""
    try:
        import importlib.util
        fix_module = Path(__file__).parent.parent.parent / "evidence" / "fix_asr_errors.py"
        if fix_module.exists():
            spec = importlib.util.spec_from_file_location("fix_asr_errors", fix_module)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            corrections = getattr(mod, "ASR_CORRECTIONS", {})
            for wrong, correct in corrections.items():
                text = text.replace(wrong, correct)
    except Exception:
        pass  # 修正模块不可用时静默跳过
    return text


def load_step_env():
    """读取步骤环境文件"""
    env = {}
    if Path(STEP_ENV).exists():
        with open(STEP_ENV, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    env[k] = v
    return env


def save_step_env(env):
    """保存步骤环境文件"""
    with open(STEP_ENV, 'w', encoding='utf-8') as f:
        for k, v in env.items():
            f.write(f"{k}={v}\n")


def extract_vtt_to_txt(vtt_path, txt_path):
    """从 VTT 提取文本内容到 TXT"""
    try:
        with open(vtt_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"  ❌ 读取 VTT 失败：{e}")
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
        text = '\n'.join(output_lines)
        text = _apply_asr_corrections(text)
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"  ✅ 已保存：{txt_path.name}")
        return True
    except Exception as e:
        print(f"  ❌ 写入 TXT 失败：{e}")
        return False


def transcribe_with_whisper(video_path, output_dir, model_size="base"):
    """使用 Whisper 转录视频"""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("  ❌ faster-whisper 未安装，请运行：pip install faster-whisper")
        return None

    video_path = Path(video_path)
    stem = video_path.stem
    vtt_path = Path(output_dir) / f"{stem}.vtt"
    txt_path = Path(output_dir) / f"{stem}.txt"

    # 跳过已存在的字幕
    if vtt_path.exists() and txt_path.exists():
        print(f"  ✓ 字幕已存在（跳过 Whisper）")
        return str(txt_path)

    print(f"  🎙️  加载 Whisper 模型：{model_size}...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    # 提取音频
    wav_path = Path(f"/tmp/{stem}.wav")
    print(f"  🔊 提取音频...")

    try:
        import subprocess
        subprocess.run([
            "/opt/homebrew/bin/ffmpeg", '-i', str(video_path),
            '-vn', '-acodec', 'pcm_s16le',
            '-ar', '16000', '-ac', '1', '-y', str(wav_path)
        ], capture_output=True, timeout=300, check=True)
    except Exception as e:
        print(f"  ❌ 提取音频失败：{e}")
        return None

    file_size_mb = wav_path.stat().st_size / 1024 / 1024
    print(f"  📊 音频：{file_size_mb:.0f}MB，开始转录...")

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
            print(f"  ⚠️  仅转录 {len(txt_lines)} 个分段，可能未成功")
            return None

        # 保存 VTT
        vtt_path.parent.mkdir(parents=True, exist_ok=True)
        vtt_path.write_text("\n".join(vtt_lines), encoding="utf-8")

        # 保存 TXT (应用 ASR 修正)
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        txt_content = " ".join(txt_lines)
        txt_content = _apply_asr_corrections(txt_content)
        txt_path.write_text(txt_content, encoding="utf-8")

        print(f"  ✅ 转录完成：{len(txt_lines)} 个分段，{len(' '.join(txt_lines))} 字")

        # 清理临时文件
        wav_path.unlink(missing_ok=True)
        return str(txt_path)

    except Exception as e:
        print(f"  ❌ 转录失败：{e}")
        wav_path.unlink(missing_ok=True)
        return None


def main():
    print("\n" + "="*70)
    print("📝 第 2 步：生成字幕")
    print("="*70 + "\n")

    # 读取环境文件
    env = load_step_env()
    video_path = env.get('VIDEO_PATH')

    # 命令行参数优先
    if len(sys.argv) > 1:
        video_path = sys.argv[1]

    if not video_path:
        print("❌ 无法获取 VIDEO_PATH")
        sys.exit(1)

    video_path = Path(video_path)
    if not video_path.exists():
        print(f"❌ 视频文件不存在：{video_path}")
        sys.exit(1)

    print(f"🎬 视频：{video_path.name}")
    print(f"📂 所在目录：{video_path.parent}")

    # 字幕输出目录
    output_dir = video_path.parent
    stem = video_path.stem
    txt_path = output_dir / f"{stem}.txt"
    vtt_path = output_dir / f"{stem}.vtt"

    # 优先检查 TXT（最终格式）- 如果已存在直接用
    if txt_path.exists():
        print(f"\n✓ 字幕已存在：{txt_path.name}")
        txt_size = txt_path.stat().st_size
        print(f"  📄 文件大小：{txt_size} 字节")
        env['TRANSCRIPT_PATH'] = str(txt_path)
        save_step_env(env)
        print("✅ 字幕准备完成（使用现有文件）")
        return

    # 检查 VTT（yt-dlp 自动生成）
    if vtt_path.exists():
        print(f"\n✓ 发现 VTT 字幕：{vtt_path.name}")
        print("  转换 VTT 为纯文本...")
        if extract_vtt_to_txt(vtt_path, txt_path):
            env['TRANSCRIPT_PATH'] = str(txt_path)
            save_step_env(env)
            print("✅ 字幕准备完成（从 VTT 转换）")
            return
        else:
            print("  VTT 转换失败，尝试 Whisper...")

    # 如果没有 VTT/TXT，运行 Whisper
    print(f"\n🎙️  使用 Whisper 生成字幕...")
    result = transcribe_with_whisper(str(video_path), str(output_dir), model_size="base")

    if result:
        env['TRANSCRIPT_PATH'] = result
        save_step_env(env)
        print("\n✅ 字幕生成完成（使用 Whisper）")
    else:
        print("\n❌ 字幕生成失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
