# YouTube 转录管道 TODO

**最后更新**: 2026-03-28 23:45
**状态**: Phase 1 完成 ✓ | Phase 2 运行中 ⏳ (脚本修复) | Phase 3 已停止 ⏸

---

## Phase 1: 清理 & 路径修复 ✓

- [x] 删除 Henry 的慢思考 `.webm.part` 文件 (1ZsjCdluO6c)
- [x] 删除 老厉害 XzW-IYZK0_8 相关 `.part` + `.ytdl` 文件 (3个)
- [x] 删除 老厉害 M91VUq7GMqM 孤儿 `.part` + `.ytdl` 文件 (3个)
- [x] 删除 老厉害 zPtU7BXJTu4 `.part` 文件 (1个)
- [x] 更新 `/Users/dereky/gemini/scripts/download_youtube_channel.sh` 行33
- [x] 更新 `Henry 的慢思考/generate_transcripts.sh` 行2
- [x] 更新 `Henry 的慢思考/process_transcripts.py` 行5
- [x] 合并 download_archive.txt (旧路径无文件)

---

## Phase 2: 转录 ⏳

### 2.1 VTT → TXT 转换

- [x] 执行 VTT→TXT 转换脚本
  ```bash
  python3 /Users/dereky/gemini/data/raw/media/youtube_downloads/vtt_to_txt.py
  ```
  **预计时间**: <1分钟

| 频道 | VTT文件数 | 目标 |
|------|---------|------|
| Henry 的慢思考 | 2 | 转换为.txt |
| 老厉害 | 71 | 转换为.txt |
| **合计** | **73** | **完成VTT转换** |

### 2.2 Whisper 转录

- [x] 执行转录脚本 (启动于 2026-03-28 22:30, PID: 21233)
  ```bash
  /Users/dereky/gemini/data/raw/media/youtube_downloads/transcribe_all.sh
  ```
  **预计时间**: Henry ~4-8小时 + 老厉害 ~2-4小时

| 频道 | 无转录视频数 | 模型 | 语言 |
|------|----------|------|------|
| Henry 的慢思考 | 20 | large-v3-turbo | zh |
| 老厉害 | 12 | large-v3-turbo | zh |
| **合计** | **32** | **待转录** | |

**需转录视频列表（Henry 的慢思考）**:
1. 20260130 - 中國長鑫存儲能否卷死三星和美光 [OEf7TNieRY4]
2. 20260201 - 散户投资进阶的过程 [mA61u_Eg8ag]
3. 20260201 - 黄金白银恐慌性暴跌 [e2eXLTK13-8]
4. 20260204 - AMD财报全面超预期 [iL8IbdhdWhY]
5. 20260206 - Amazon 2000亿美元的股市震撼弹 [KaMxAJVcdZQ]
6. 20260208 - 牛市来了,还是陷阱 [8FG_1es_GkY]
7. 20260210 - 美光股价崩盘15% [K16p8aJfJUM]
8. 20260211 - 如何投资SpaceX [WZoVmOmfFC4]
9. 20260215 - 股市看不见的风险 [PdJEZcRV-UY]
10. 20260217 - 史诗级的short squeeze要来了 [j08V-mkuWPk]
11. 20260218 - 5周暴涨320% [rN7nlAjfZDM]
12. 20260219 - 美国打伊朗 [PnrvQL2T_ck]
13. 20260223 - 股市过山车 [ir2NMBmH4yM]
14. 20260225 - Nvidia是好公司 [_lyWqelvhIc]
15. 20260227 - 知识经济雪崩 [tZ3TbJqvG4w]
16. 20260301 - 牛市末期 [YKeVu9SlqFE]
17. 20260304 - 霍尔木兹一封 [B6Sw8KXVX44]
18. 20260306 - 贵得离谱 [fSzbgDvzDlU]
19. 20260309 - 伊朗危机 [EDIfXvPDO3Y]
20. ~~20260220 - 我给观众的投资建议~~ （已有.txt）

---

## Phase 3: 下载新视频 ⏳

- [x] 重新下载 M91VUq7GMqM 视频 ✓ (耗时 1m7s, 完成于 22:35)
- [x] 下载新视频 (两个频道) — **运行中** (PID: 21372, 已发现新视频 YA8I6JWSPk4)
- [ ] 转录新下载的视频 (待下载完成)

---

## 转录覆盖率进度表

### Henry 的慢思考

| 指标 | 当前 | 目标 |
|------|------|------|
| 总视频数 | 25 | - |
| 已有.txt数 | 7 | 25 |
| .vtt待转.txt | 2 | 0 |
| 无转录文件 | 16 | 0 |
| **覆盖率** | **28%** | **100%** |

### 老厉害

| 指标 | 当前 | 目标 |
|------|------|------|
| 总视频数 | 94 | - |
| 已有.txt数 | 22 | 94 |
| .vtt待转.txt | 71 | 0 |
| 无转录文件 | 1 | 0 |
| **覆盖率** | **~23%** | **100%** |

---

## 工具参考

| 工具 | 路径 | 版本/模型 |
|------|------|--------|
| whisper | `/opt/homebrew/bin/whisper` | large-v3-turbo |
| ffmpeg | `/opt/homebrew/bin/ffmpeg` | v8.0.1 |
| yt-dlp | `/Users/dereky/gemini/mem0-venv/bin/yt-dlp` | v2026.03.17 |
| cookies | `/Users/dereky/gemini/data/raw/media/youtube_downloads/cookies.txt` | - |

---

## 验证方法

**Phase 2 完成后验证**:
```bash
# Henry: 检查 .txt 覆盖率
cd "/Users/dereky/gemini/data/raw/media/youtube_downloads/Henry 的慢思考"
echo "MP4 files: $(ls -1 *.mp4 2>/dev/null | wc -l)"
echo "TXT files: $(ls -1 *.txt 2>/dev/null | wc -l)"

# 老厉害: 检查 .txt 覆盖率
cd "/Users/dereky/gemini/data/raw/media/youtube_downloads/老厉害"
echo "Video files: $(ls -1 *.mp4 *.webm 2>/dev/null | wc -l)"
echo "TXT files: $(ls -1 *.txt 2>/dev/null | wc -l)"
```

**成功标准**: 两个频道均达到 **100%** .txt 覆盖率 ✓

---

## 注意事项

- ⚠️ Whisper 转录可能耗时较长，建议在后台运行或分频道执行
- ⚠️ WebM 文件需通过 ffmpeg 提取音频后才能转录（MP4可直接调用）
- ⚠️ M91VUq7GMqM 重新下载前需确保网络稳定
- ✓ VTT→TXT 转换已验证成功（逻辑来自现有 process_transcripts.py）
