#!/usr/bin/env python3
"""
验证自动化流程完整性（不调用真实 LLM）
"""

import json
import sys
from pathlib import Path
from config import CHECKLIST_PATH, YOUTUBE_DIR, REPORTS_DIR

def verify_checklist():
    """验证 checklist 结构"""
    print("\n✅ 验证 checklist.json 结构:")
    with open(CHECKLIST_PATH) as f:
        checklist = json.load(f)

    assert "enabled" in checklist
    assert "videos" in checklist
    assert "last_scanned" in checklist

    videos = checklist["videos"]
    print(f"   📊 总视频数: {len(videos)}")

    # 统计状态
    status_counts = {}
    for video_info in videos.values():
        status = video_info.get("report_status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    for status, count in sorted(status_counts.items()):
        print(f"      {status}: {count}")

    # 验证必需字段
    sample_video = next(iter(videos.values()))
    required_fields = ["title", "channel", "date", "has_transcript", "report_status", "report_path", "processed_at"]
    for field in required_fields:
        assert field in sample_video, f"缺少字段: {field}"

    print("   ✅ Checklist 结构正确")
    return True


def verify_directory_structure():
    """验证目录结构"""
    print("\n✅ 验证目录结构:")

    # 检查必需的目录
    dirs_to_check = [
        Path(YOUTUBE_DIR) / "Henry 的慢思考",
        Path(YOUTUBE_DIR) / "老厉害",
        Path(REPORTS_DIR) / "Henry 的慢思考",
        Path(REPORTS_DIR) / "老厉害",
    ]

    for dir_path in dirs_to_check:
        assert dir_path.exists(), f"目录不存在: {dir_path}"
        print(f"   ✅ {dir_path}")

    print("   ✅ 目录结构完整")
    return True


def verify_config():
    """验证配置文件"""
    print("\n✅ 验证配置文件:")

    from config import (
        ENABLED, BAILIAN_API_KEY, BAILIAN_BASE_URL, BAILIAN_MODEL,
        TAVILY_API_KEY, TAVILY_MAX_RESULTS,
        CHANNELS, YOUTUBE_DIR, REPORTS_DIR
    )

    print(f"   ENABLED: {ENABLED}")
    print(f"   BAILIAN_MODEL: {BAILIAN_MODEL}")
    print(f"   TAVILY_API_KEY: {'✅ 已配置' if TAVILY_API_KEY else '❌ 未配置'}")
    print(f"   BAILIAN_API_KEY: {'✅ 已配置' if BAILIAN_API_KEY else '⚠️  未配置（用户需填入）'}")
    print(f"   CHANNELS: {CHANNELS}")

    print("   ✅ 配置检查完成")
    return True


def verify_transcript_availability():
    """验证字幕文件可用性"""
    print("\n✅ 验证字幕文件可用性:")

    with open(CHECKLIST_PATH) as f:
        checklist = json.load(f)

    videos_with_transcript = [
        v for v in checklist["videos"].values()
        if v.get("has_transcript")
    ]

    print(f"   📄 有字幕的视频: {len(videos_with_transcript)} / {len(checklist['videos'])}")

    if videos_with_transcript:
        # 检查第一个视频的字幕文件是否真的存在
        sample = videos_with_transcript[0]
        channel = sample["channel"]
        video_id = None

        # 从 checklist 中查找
        for vid, info in checklist["videos"].items():
            if info == sample:
                video_id = vid
                break

        if video_id:
            transcript_file = Path(YOUTUBE_DIR) / channel / f"{video_id}.txt"
            if transcript_file.exists():
                size = transcript_file.stat().st_size
                print(f"   ✅ 示例字幕: {video_id}.txt ({size} 字节)")
            else:
                print(f"   ❌ 字幕文件不存在: {transcript_file}")
                return False

    print("   ✅ 字幕检查完成")
    return True


def verify_pipeline_executable():
    """验证 pipeline.py 可执行"""
    print("\n✅ 验证 pipeline.py 可执行:")

    # 简单检查是否能导入
    try:
        import pipeline
        print("   ✅ pipeline.py 可导入")
    except Exception as e:
        print(f"   ❌ pipeline.py 导入失败: {e}")
        return False

    return True


def verify_report_generator_structure():
    """验证 report_generator.py 结构"""
    print("\n✅ 验证 report_generator.py 结构:")

    try:
        import report_generator
        # 检查关键函数
        functions = [
            "load_checklist",
            "load_transcript",
            "generate_report",
            "test_single_video",
            "fetch_tavily_counterpoints",
            "generate_report_with_bailian"
        ]

        for func_name in functions:
            if hasattr(report_generator, func_name):
                print(f"   ✅ {func_name}()")
            else:
                print(f"   ❌ 缺少函数: {func_name}()")
                return False

        print("   ✅ report_generator.py 结构完整")
        return True

    except Exception as e:
        print(f"   ❌ report_generator.py 导入失败: {e}")
        return False


def main():
    print("="*60)
    print("🔧 自动化流程完整性验证")
    print("="*60)

    checks = [
        verify_config,
        verify_directory_structure,
        verify_checklist,
        verify_transcript_availability,
        verify_pipeline_executable,
        verify_report_generator_structure,
    ]

    results = []
    for check in checks:
        try:
            result = check()
            results.append(result)
        except AssertionError as e:
            print(f"   ❌ 验证失败: {e}")
            results.append(False)
        except Exception as e:
            print(f"   ❌ 错误: {e}")
            results.append(False)

    print("\n" + "="*60)
    if all(results):
        print("✅ 所有验证通过！自动化流程已准备就绪")
        print("\n📋 下一步:")
        print("  1. 在 config.py 中填入 BAILIAN_API_KEY")
        print("  2. 设置 ENABLED = True 以启用自动处理")
        print("  3. 运行: python3 report_generator.py --test <video_id>")
        print("="*60)
        return 0
    else:
        print("❌ 某些验证失败，请检查上述错误信息")
        print("="*60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
