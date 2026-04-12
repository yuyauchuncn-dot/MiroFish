#!/usr/bin/env python3
"""
Update checklist.json paths from absolute gemini paths to MONO_ROOT-relative paths.
Channel names are preserved exactly as-is (e.g., "張經義", "Henry 的慢思考").
"""

import json
from pathlib import Path

CHECKLIST = Path(__file__).parent / "checklist.json"
GEMINI_PREFIX = "/Users/dereky/gemini/"

with open(CHECKLIST, "r", encoding="utf-8") as f:
    data = json.load(f)

updated = 0
for video_id, entry in data.get("videos", {}).items():
    # Fix transcript_path — keep original channel name
    if "transcript_path" in entry and entry["transcript_path"]:
        old = entry["transcript_path"]
        if old.startswith(GEMINI_PREFIX):
            entry["transcript_path"] = old[len(GEMINI_PREFIX):]
            updated += 1

    # Fix report_path — keep original channel name
    if "report_path" in entry and entry["report_path"]:
        old = entry["report_path"]
        if old.startswith(GEMINI_PREFIX):
            rel = old[len(GEMINI_PREFIX):]
            # Replace data/reports/youtube/{channel} with monodata/reports/youtube/{channel}
            if rel.startswith("data/reports/youtube/"):
                parts = rel.split("/", 4)  # data/reports/youtube/{channel}/{filename}
                if len(parts) >= 5:
                    channel_name = parts[3]  # Keep original channel name
                    entry["report_path"] = f"monodata/reports/youtube/{channel_name}/{parts[4]}"
                else:
                    entry["report_path"] = "monodata/" + rel
            else:
                entry["report_path"] = "monodata/" + rel
            updated += 1

with open(CHECKLIST, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"Updated {updated} path entries in checklist.json")

# Verify no gemini paths remain
with open(CHECKLIST, "r", encoding="utf-8") as f:
    content = f.read()
gemini_count = content.count("/Users/dereky/gemini/")
print(f"Remaining /Users/dereky/gemini/ references: {gemini_count}")
