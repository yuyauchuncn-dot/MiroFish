# YouTube 频道下载器

本脚本可高效下载 YouTube 频道中的所有视频及其**中英文字幕**。

设计**智能且节省流量**：
- **不会重复下载** `youtube_downloads` 目录中已有的视频
- 通过归档文件（`youtube_downloads/download_archive.txt`）跟踪已下载视频，可重复运行，仅获取新内容

## 使用方法

脚本已创建并赋予执行权限。下载所有缺失视频和字幕：

```bash
./scripts/download_youtube_channel.sh
```

脚本会自动将新视频和 `.vtt` 字幕文件放入 `./youtube_downloads/老厉害/` 目录，按上传日期命名。
