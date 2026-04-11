# YouTube Downloads - Memory

## Channel: @oldpowerful (老厉害)
- **Total videos**: 279
- **Downloaded**: 87
- **Archive**: `download_archive.txt` (tracks completed downloads)
- **Cookies**: `cookies.txt` (for yt-dlp)

## Download Command
```bash
cd /Users/dereky/gemini/youtube_downloads
yt-dlp --cookies cookies.txt --write-auto-sub --write-sub --sub-lang en --sub-lang zh --convert-subs srt -f "bestvideo[height<=1080]+bestaudio/best" --merge-output-format mp4 --output "%(upload_date)s - %(title)s [%(id)s].%(ext)s" --download-archive download_archive.txt https://www.youtube.com/@oldpowerful/videos
```

## Status (2026-03-15)
- YouTube SABR streaming causes slow downloads
- Stopped by DY — can resume anytime with the command above
- Download archive tracks progress, safe to restart

## Henry 的慢思考 (25 videos)
- Location: `Henry 的慢思考/`
- 22 of 25 need transcripts (whisper)
- Whisper task was running as subagent — check completion
