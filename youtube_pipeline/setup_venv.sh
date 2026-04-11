#!/bin/bash

# 虛擬環境自動設置腳本
echo "🔧 開始設置虛擬環境..."

# 切換到正確目錄
cd ~/gemini/youtube_downloads

# 創建虛擬環境
python3 -m venv venv

# 啟用虛擬環境
source venv/bin/activate

# 安裝必要套件
pip install selenium webdriver-manager gdown yt-dlp faster-whisper beautifulsoup4 requests

# 驗證安裝
echo "✅ 虛擬環境設置完成！"
echo ""
echo "使用方式："
echo "  source ~/gemini/youtube_downloads/venv/bin/activate"
echo ""
echo "測試命令："
echo "  python -c \"import selenium; print('Selenium:', selenium.__version__)\""
echo "  python -c \"import gdown; print('gdown installed')\""
echo "  python -c \"import yt_dlp; print('yt-dlp:', yt_dlp.version.__version__)\""
echo ""
echo "現在你可以運行："
echo "  1. python ~/gemini/youtube_downloads/web_mcp_update_cookies.py"
echo "  2. gdown \"https://drive.google.com/file/d/1MAbtUBudFMXLSB6yaf-o5SwcVXulIAkK/view\" -O ~/gemini/research/oldpowerful_研報.pdf"