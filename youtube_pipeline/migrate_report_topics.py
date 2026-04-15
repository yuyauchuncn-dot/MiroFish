#!/usr/bin/env python3
"""Backfill topic categories into existing report filenames.

Tier 1: Extract topic from v4 report H1 heading (zero LLM)
Tier 2: Run classify_topic_v2 on v3 report transcripts (zero LLM, pure keyword matching)

Usage:
    python migrate_report_topics.py --dry-run   # preview only
    python migrate_report_topics.py             # execute renames
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

# ── Path setup ─────────────────────────────────────────────────────
_script_dir = Path(__file__).resolve().parent
_mono_root = _script_dir.parent.parent
sys.path.insert(0, str(_mono_root))
sys.path.insert(0, str(_mono_root / "mirofish" / "src"))

from monofetchers.config import MONO_ROOT
from v4.topic_config import classify_topic_v2, TopicCategory, TOPIC_CONFIGS

REPORTS_DIR = Path(MONO_ROOT) / "monodata" / "reports" / "youtube"
TRANSCRIPTS_DIR = Path(MONO_ROOT) / "monodata" / "raw" / "youtube"
CHECKLIST_PATH = _script_dir / "checklist.json"

# v4 H1 title → TopicCategory mapping
_V4_H1_MAP: dict[str, TopicCategory] = {}
for cat, cfg in TOPIC_CONFIGS.items():
    _V4_H1_MAP[cfg.display_name] = cat


def find_transcript(channel: str, report_path: Path) -> Path | None:
    """Find matching transcript for a report file."""
    # Extract video_id from report filename: ... [VIDEO_ID]_v4_MiroFish.md or ... [VIDEO_ID]_MiroFish.md
    stem = report_path.stem
    m = re.search(r'\[([^\]]+)\]', stem)
    if m:
        video_id = m.group(1)
        # Search in channel's transcript dir
        ch_dir = TRANSCRIPTS_DIR / channel
        if ch_dir.exists():
            for ext in (".txt", ".vtt"):
                candidates = list(ch_dir.rglob(f"*{video_id}*{ext}"))
                if candidates:
                    return candidates[0]
        # Also check adjacent to report
        for ext in (".txt", ".vtt"):
            candidates = list(report_path.parent.rglob(f"*{video_id}*{ext}"))
            if candidates:
                return candidates[0]
    return None


def extract_topic_from_v4_report(report_path: Path) -> TopicCategory | None:
    """Extract topic from v4 report H1 heading."""
    try:
        first_lines = report_path.read_text(encoding="utf-8", errors="ignore")[:500]
    except Exception:
        return None

    # Match H1: # MiroFish v4.0 <topic>
    h1_match = re.search(r'^#\s+MiroFish v4\.0\s+(.+?)(?:\n|$)', first_lines, re.MULTILINE)
    if h1_match:
        h1_text = h1_match.group(1).strip()
        # Try exact match
        for display_name, cat in _V4_H1_MAP.items():
            if display_name in h1_text:
                return cat
        # Partial match (e.g., "Palantir (PLTR) 深度分析" → financial)
        if "深度" in h1_text and "分析" in h1_text:
            return TopicCategory.FINANCIAL

    # Try **分析框架** line as fallback
    af_match = re.search(r'\*\*分析框架\*\*[：:]\s*(.+?)(?:\n|$)', first_lines)
    if af_match:
        af_text = af_match.group(1).strip()
        # Map common framework names to topics
        if "冲突" in af_text or "地缘" in af_text or "安全" in af_text:
            return TopicCategory.WAR_CONFLICT
        if "加密" in af_text or "区块链" in af_text:
            return TopicCategory.CRYPTO_BLOCKCHAIN
        if "房地产" in af_text or "住房" in af_text:
            return TopicCategory.REAL_ESTATE
        if "大宗" in af_text or "能源" in af_text:
            return TopicCategory.COMMODITIES
        if "宏观" in af_text or "资产配置" in af_text:
            return TopicCategory.MACRO_STRATEGY
        if "科技" in af_text or "产业" in af_text:
            return TopicCategory.TECHNOLOGY
        if "社会" in af_text:
            return TopicCategory.SOCIAL_OBSERVATION
        if "旅行" in af_text or "游民" in af_text:
            return TopicCategory.TRAVEL_NOMAD
        if "金融" in af_text or "投资" in af_text:
            return TopicCategory.FINANCIAL

    return None


def classify_v3_report(report_path: Path, channel: str) -> TopicCategory | None:
    """Run classify_topic_v2 on matching transcript."""
    transcript_path = find_transcript(channel, report_path)
    if not transcript_path or not transcript_path.exists():
        return None

    try:
        content = transcript_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    # Extract title from report filename
    stem = report_path.stem
    # Remove common suffixes: _MiroFish, _v4_MiroFish
    title_part = re.sub(r'_(v4_)?MiroFish$', '', stem)
    # Remove leading date prefix: YYYYMMDD_
    title_part = re.sub(r'^\d{8}_', '', title_part)
    # Remove [VIDEO_ID] suffix
    title_part = re.sub(r'\s*\[[^\]]+\]\s*$', '', title_part)

    if not content.strip():
        return None

    result = classify_topic_v2(content, title_part, channel)
    return result.primary


def is_v4_report(path: Path) -> bool:
    """Check if a report is a v4 report based on filename or content."""
    name = path.name
    return "_v4_" in name or "[v4_" in name


def compute_new_name(old_path: Path, topic: TopicCategory) -> str:
    """Compute new filename with topic suffix.

    _MiroFish.md → _MiroFish_{topic}.md
    _v4_MiroFish.md → _v4_MiroFish_{topic}.md
    [v4_MiroFish].md → [v4_MiroFish]_{topic}.md
    """
    name = old_path.name

    # Already has a topic suffix? Skip.
    for cat in TopicCategory:
        if name.endswith(f"_{cat.value}.md"):
            return None

    # Handle different naming patterns
    if "[v4_MiroFish]" in name:
        return name.replace("[v4_MiroFish].md", f"[v4_MiroFish]_{topic.value}.md")
    elif "_v4_MiroFish_" in name:
        # Already has some suffix (e.g., _commodities)
        return None
    elif "_v4_MiroFish.md" in name:
        return name.replace("_v4_MiroFish.md", f"_v4_MiroFish_{topic.value}.md")
    elif "_MiroFish.md" in name:
        return name.replace("_MiroFish.md", f"_MiroFish_{topic.value}.md")

    return None


def update_checklist(renames: list[tuple[str, str]]) -> None:
    """Update checklist.json report_path entries after renames."""
    if not CHECKLIST_PATH.exists():
        return

    try:
        with open(CHECKLIST_PATH, "r", encoding="utf-8") as f:
            checklist = json.load(f)
    except Exception:
        print("  Could not load checklist.json")
        return

    rename_map = {old: new for old, new in renames}
    updated = 0

    for video_id, info in checklist.get("videos", {}).items():
        old_path = info.get("report_path", "")
        if not old_path:
            continue
        # Extract filename from path
        fname = Path(old_path).name
        if fname in rename_map:
            new_fname = rename_map[fname]
            new_path = str(Path(old_path).parent / new_fname)
            info["report_path"] = new_path
            updated += 1

    if updated > 0:
        try:
            with open(CHECKLIST_PATH, "w", encoding="utf-8") as f:
                json.dump(checklist, f, ensure_ascii=False, indent=2)
            print(f"\n  Updated {updated} report_path entries in checklist.json")
        except Exception as e:
            print(f"\n  Failed to update checklist.json: {e}")


def main():
    parser = argparse.ArgumentParser(description="Backfill topic categories into report filenames")
    parser.add_argument("--dry-run", action="store_true", help="Preview renames without executing")
    args = parser.parse_args()

    print(f"{'DRY RUN' if args.dry_run else 'EXECUTING'}: Topic backfill for report filenames")
    print(f"Reports directory: {REPORTS_DIR}\n")

    all_renames = []  # (old_path_str, new_path_str, topic, channel)
    skipped = 0
    errors = 0

    # Scan all .md files
    md_files = sorted(REPORTS_DIR.rglob("*.md"))
    print(f"Found {len(md_files)} report files\n")

    for report_path in md_files:
        # Skip archived
        if "archived" in str(report_path):
            continue

        channel = report_path.parent.name
        old_name = report_path.name

        # Skip non-MiroFish reports
        if "MiroFish" not in old_name:
            skipped += 1
            continue

        # Determine topic
        topic = None

        if is_v4_report(report_path):
            # Tier 1: Extract from H1
            topic = extract_topic_from_v4_report(report_path)
            method = "v4 H1 extract"
        else:
            # Tier 2: classify_topic_v2 on transcript
            topic = classify_v3_report(report_path, channel)
            method = "v3 classify"

        if topic is None:
            skipped += 1
            if not args.dry_run:
                print(f"  SKIP (no topic): {old_name} ({channel})")
            continue

        # Compute new filename
        new_name = compute_new_name(report_path, topic)
        if new_name is None:
            # Already has topic suffix
            skipped += 1
            continue

        new_path = report_path.parent / new_name
        all_renames.append((str(report_path), str(new_path), topic.value, channel))

        if args.dry_run:
            print(f"  {method:20s} {channel:25s} {topic.value:20s}")
            print(f"    {old_name}")
            print(f"    → {new_name}")
            print()

    # Execute renames
    if not args.dry_run:
        for old_str, new_str, topic_val, channel in all_renames:
            old_p = Path(old_str)
            new_p = Path(new_str)

            if new_p.exists():
                # Collision: add numeric suffix
                base = new_p.stem
                counter = 1
                while new_p.exists():
                    new_p = new_p.parent / f"{base}_{counter}.md"
                    counter += 1

            try:
                old_p.rename(new_p)
                print(f"  RENAMED ({topic_val:20s}) {old_p.name}")
                print(f"    → {new_p.name}")
            except Exception as e:
                print(f"  ERROR: {old_p.name} → {e}")
                errors += 1

        # Update checklist
        flat_renames = [(Path(o).name, Path(n).name) for o, n, _, _ in all_renames]
        update_checklist(flat_renames)

    # Summary
    print(f"\n{'='*60}")
    print(f"{'DRY RUN SUMMARY' if args.dry_run else 'MIGRATION COMPLETE'}")
    print(f"{'='*60}")
    print(f"  Reports scanned:  {len(md_files)}")
    print(f"  Renames planned:  {len(all_renames)}")
    print(f"  Skipped:          {skipped}")
    print(f"  Errors:           {errors}")

    # Topic distribution
    if all_renames:
        from collections import Counter
        topic_dist = Counter(r[2] for r in all_renames)
        print(f"\n  Topic distribution:")
        for topic_val, count in topic_dist.most_common():
            bar = "█" * count
            print(f"    {topic_val:25s} {count:4d}  {bar}")

    # Write CSV log
    csv_path = _script_dir / f"report_topics_{'dryrun' if args.dry_run else 'migrated'}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["old_path", "new_path", "topic", "channel"])
        for old_str, new_str, topic_val, channel in all_renames:
            writer.writerow([Path(old_str).name, Path(new_str).name, topic_val, channel])
    print(f"\n  CSV log: {csv_path}")


if __name__ == "__main__":
    main()
