#!/usr/bin/env python3
"""
自動更新 YouTube cookies 用於 yt-dlp
使用 Selenium + ChromeDriver 自動抓取最新 cookies
"""

import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from pathlib import Path

def update_youtube_cookies(cookie_path):
    """自動抓取 YouTube cookies 並儲存"""

    print("🔧 開始自動更新 YouTube cookies...")

    # Chrome 選項
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # 無頭模式
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # 啟動 Chrome
    driver = None
    try:
        driver = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()),
            options=chrome_options
        )

        # 訪問 YouTube
        driver.get("https://www.youtube.com")
        print("⏳ 等待頁面載入...")
        time.sleep(5)

        # 檢查是否已登入（檢查用戶頭像是否存在）
        try:
            # 嘗試找登入按鈕，如果存在表示未登入
            login_btn = driver.find_elements_by_xpath('//*[@id="buttons"]/a[contains(@href, "accounts.google.com")]')
            if login_btn:
                print("⚠️  YouTube 未登入！請先手動登入一次後再執行此腳本")
                driver.quit()
                return False
        except:
            pass

        # 抓取所有 cookies
        cookies = driver.get_cookies()
        print(f"✅ 成功抓取 {len(cookies)} 個 cookies")

        # 儲存到檔案
        cookie_path = Path(cookie_path)
        cookie_path.parent.mkdir(parents=True, exist_ok=True)

        with open(cookie_path, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, indent=2, ensure_ascii=False)

        print(f"✅ Cookies 已儲存至: {cookie_path}")

        # 驗證有效性（簡短測試）
        print("🔍 驗證 cookies 有效性...")
        test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Rick Roll (safe test)
        driver.get(test_url)
        time.sleep(3)

        # 檢查頁面是否正常載入（檢查 title 是否包含 "YouTube"）
        if "YouTube" in driver.title:
            print("✅ Cookies 驗證成功！")
            result = True
        else:
            print("❌ Cookies 驗證失敗，可能需要重新登入")
            result = False

        driver.quit()
        return result

    except Exception as e:
        print(f"❌ 錯誤: {e}")
        if driver:
            driver.quit()
        return False

if __name__ == "__main__":
    cookie_file = Path.home() / ".openclaw" / "workspace" / "cookies.txt"
    success = update_youtube_cookies(cookie_file)
    exit(0 if success else 1)
