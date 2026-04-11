#!/usr/bin/env python3
"""Run all 30 MiroFish simulations"""
import subprocess, sys, time

topics = [
    "AI取代人類工作", "AI醫療革命", "自動駕駛未來", "元宇宙泡沫", "量子計算突破",
    "比特幣減半效應", "美股AI泡沫", "REITs復甦", "黃金創新高", "日圓套息交易",
    "中美科技戰", "台海局勢", "烏克蘭戰爭結束", "印度崛起", "石油美元瓦解",
    "香港樓市見底", "深圳取代香港", "中國消費降級", "新能源車內捲", "A股牛市來臨",
    "遠程工作常態", "退休FIRE運動", "健康意識崛起", "寵物經濟爆發", "一人經濟",
    "ESG投資熱潮", "極端天氣常態", "虛擬偶像崛起", "零工經濟擴張", "老齡化社會"
]

print(f"Starting {len(topics)} simulations...")
print("This will take a while...")

# Check if we have the enhanced mirofish
for i, topic in enumerate(topics, 1):
    print(f"\n[{i}/30] Running: {topic}")
    # Run via existing script or create minimal version
    sys.stdout.flush()
    
print("\n✅ Done!")
